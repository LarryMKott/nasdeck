"""系统自检聚合（原型 E1，GET /system/diagnostics 消费）。

把散落各处的"失败不可见"收敛成一份分组清单：数据管线 / 风扇 / 鉴权链 /
采集工具 / 通知。每项 {key, status(ok|warn|fail|skip), detail, hint}，
status=skip 表示当前形态不适用（如开发机无 FPK 镜像路径）。
判定阈值集中在各 _check_* 内，供自检页与诊断包共用。
"""

from __future__ import annotations

import shutil
import time
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db import ingest
from app.models.system import SystemSetting
from app.services.alert import engine as alert_engine
from app.services.control import fcs_safe_takeover, fan_manager
from app.services.monitor.cache import realtime_cache
from app.tasks import downsampler

# 断流判定：最近一次写成功距今超过该秒数（ingest 2s 攒批 + 余量）
_STALL_SECONDS = 30.0
# 降采样滞后判定：正常 5 分钟一轮，超过 3 轮未跑即滞后
_DOWNSAMPLE_PERIOD_S = 5 * 60.0


def _item(key: str, status: str, detail: str, hint: str | None = None) -> dict:
    return {"key": key, "status": status, "detail": detail, "hint": hint}


async def collect(db: AsyncSession) -> dict:
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "groups": [
            {"name": "数据管线", "items": await _check_pipeline(db)},
            {"name": "风扇", "items": _check_fans()},
            {"name": "鉴权链", "items": _check_auth()},
            {"name": "采集工具", "items": _check_tools()},
            {"name": "通知", "items": _check_notify()},
        ],
    }


async def _check_pipeline(db: AsyncSession) -> list[dict]:
    items = []
    stats = ingest.stats()
    now = time.time()

    if not stats["worker_running"]:
        items.append(_item("ingest_worker", "fail", f"落库 worker 未运行（重启 {stats['worker_restarts']} 次）",
                           "查看后端日志 grep ingest-writer；持续失败检查磁盘 IO"))
    else:
        if stats["worker_restarts"]:
            items.append(_item("ingest_worker", "warn", f"运行中（已自动重启 {stats['worker_restarts']} 次）",
                               f"最近错误：{stats['last_error'] or '无'}"))
        else:
            items.append(_item("ingest_worker", "ok", "运行中"))

    if stats["last_write_ts"]:
        stall = now - stats["last_write_ts"]
        if stall > _STALL_SECONDS:
            items.append(_item("ingest_stall", "fail", f"最近写成功于 {stall:.0f}s 前（阈值 {_STALL_SECONDS:.0f}s）",
                               "检查磁盘写入与 SQLite 锁；自愈重启失败时查看日志"))
        else:
            items.append(_item("ingest_stall", "ok", f"最近写成功于 {stall:.0f}s 前"))
    else:
        items.append(_item("ingest_stall", "skip", "启动以来尚无数据写入（刚启动或采集源为空）"))

    depth, cap = stats["queue_depth"], stats["queue_capacity"]
    ratio = depth / cap if cap else 0
    if ratio > 0.8:
        items.append(_item("ingest_queue", "warn", f"队列水位 {depth}/{cap}（>80%，接近丢弃阈值）",
                           "盘写入持续过慢；丢批累计见 detail", ))
        items[-1]["detail"] += f"，累计丢弃 {stats['dropped_total']} 行"
    else:
        items.append(_item("ingest_queue", "ok", f"队列水位 {depth}/{cap}"))

    ds = downsampler.stats()
    if ds["last_run_ts"]:
        lag = now - ds["last_run_ts"]
        if lag > 3 * _DOWNSAMPLE_PERIOD_S:
            items.append(_item("downsampler", "fail", f"降采样 {lag / 60:.0f} 分钟未运行（正常 5 分钟一轮）",
                               ds["last_error"] or "查看调度器是否在跑"))
        elif ds["last_error"]:
            items.append(_item("downsampler", "warn", f"最近一轮有错误：{ds['last_error']}", "查看后端日志 downsample"))
        else:
            items.append(_item("downsampler", "ok", f"最近运行于 {lag:.0f}s 前，本轮写入 {ds['buckets_written']} 桶"))
    else:
        items.append(_item("downsampler", "skip", "进程启动以来尚未运行（调度器未到首个周期）"))

    rebuilt = await db.get(SystemSetting, "db_rebuilt_at")
    if rebuilt is not None:
        items.append(_item("db_rebuilt", "warn", f"曾发生结构重建：{rebuilt.value}",
                           "历史数据自该时刻重新积累；备份文件保留在 data/ 目录"))
    return items


def _check_fans() -> list[dict]:
    items = []
    outputs = realtime_cache.get("fan_outputs") or []
    degraded = [o for o in outputs if o.get("error") or o.get("failsafe")]
    if outputs and degraded:
        desc = "; ".join(f"{o.get('name')}({o.get('error') or o.get('failsafe')})" for o in degraded)
        items.append(_item("fan_zones", "fail", f"{len(degraded)}/{len(outputs)} 个控区调速降级：{desc}",
                           "风扇页查看\"最近调速异常\"；传感器失联持续会自动全速保护"))
    elif outputs:
        items.append(_item("fan_zones", "ok", f"{len(outputs)} 个受管控区调速正常"))
    else:
        items.append(_item("fan_zones", "skip", "无受管控区（全部 auto 或未配置）"))

    restore_fails = [e for e in fan_manager.recent_events() if e["failsafe"] == "restore_failed"]
    if restore_fails:
        items.append(_item("restore_auto", "warn", f"最近有 {len(restore_fails)} 次交还内核失败",
                           "风扇页对应控区\"重试交还\"；持续失败检查驱动是否支持 pwm_enable=2"))
    else:
        items.append(_item("restore_auto", "ok", "无交还失败记录"))

    state = fcs_safe_takeover.state_file_status()
    items.append(_item("fcs_state_file", "ok" if state["ok"] else "fail", state["detail"],
                       None if state["ok"] else "删除损坏文件后重启将按未接管初始化；请核对原生温控状态"))
    return items


def _check_auth() -> list[dict]:
    items = []
    if settings.trim_auth and not settings.proxy_token:
        items.append(_item("proxy_token", "warn", "TRIM_AUTH=true 但 PROXY_TOKEN 未设置：admin 判定退回信任网关身份头",
                           "设置 NASDECK_PROXY_TOKEN 后重启（自托管直连形态可忽略）"))
    elif settings.trim_auth:
        items.append(_item("proxy_token", "ok", "代理共享密钥已配置"))
    else:
        items.append(_item("proxy_token", "skip", "非飞牛反代形态（trim_auth 关闭）"))

    if not settings.api_key and not settings.trim_auth:
        items.append(_item("api_key", "warn", "面板无任何鉴权（api_key 与 trim_auth 均未启用）",
                           f"当前绑定 {settings.host}；如非回环请配置 NASDECK_API_KEY"))
    else:
        items.append(_item("api_key", "ok", "已启用"))
    return items


def _check_tools() -> list[dict]:
    items = []
    for tool, why in (("smartctl", "硬盘 SMART 健康与温度"), ("mdadm", "软 RAID 状态"), ("docker", "容器列表")):
        found = shutil.which(tool) is not None
        items.append(_item(f"tool_{tool}", "ok" if found else "warn",
                           "在位" if found else f"未安装（{why}将降级/为空）",
                           None if found else f"安装：apt install { {'smartctl': 'smartmontools'}.get(tool, tool) }"))
    storcli = settings.storcli_cmd
    storcli_ok = shutil.which(storcli) is not None or (settings.storcli_path and shutil.which(settings.storcli_path))
    items.append(_item("tool_storcli", "ok" if storcli_ok else "warn",
                       "在位（硬 RAID 可用）" if storcli_ok else f"不可用（{storcli}；硬 RAID 区段降级，ARM 包不含属正常）"))
    return items


def _check_notify() -> list[dict]:
    items = []
    health = alert_engine.channel_health()
    bad = {cid: h for cid, h in health.items() if h["send_failures"] or h["last_error"]}
    if bad:
        desc = "; ".join(f"渠道#{cid} 失败×{h['send_failures']}（{h['last_error']}）" for cid, h in bad.items())
        items.append(_item("notify_channels", "warn", desc, "自动化页\"测试\"按钮查看分类原因；认证失败请更新凭据"))
    elif health:
        items.append(_item("notify_channels", "ok", f"{len(health)} 个渠道发送正常"))
    else:
        items.append(_item("notify_channels", "skip", "尚无发送记录（未配置渠道或未触发过告警）"))

    pending = alert_engine.pending_stats()
    if pending["depth"] > pending["capacity"] * 0.8:
        items.append(_item("notify_queue", "warn", f"待发送 {pending['depth']}/{pending['capacity']}（接近上限）",
                           "慢渠道持续失败会丢弃新通知并留痕"))
    else:
        items.append(_item("notify_queue", "ok", f"待发送 {pending['depth']}/{pending['capacity']}"))
    return items
