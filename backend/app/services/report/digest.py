"""周报生成与推送（M3.1）：定时摘要 + HTML 报告链接，经全部启用渠道发送。

摘要口径（全部真实采集/落库数据，无造数）：7 天内事件数（触发/恢复分列）、
当前 firing 数、最高温（metric_points 10m/1m 桶最大值）、各卷容量与写满预测、
磁盘健康分布。调度走 system_settings 键 report_schedule（星期+小时）与
report_last_run 周去重——selftest_schedule 同款 10 分钟拍模式；手动立即发送
（POST /system/report/send）供调试与验收。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import AlertEvent
from app.models.metrics import MetricPoint
from app.models.system import SystemSetting
from app.services.storage import capacity

logger = logging.getLogger(__name__)

SCHEDULE_KEY = "report_schedule"
LAST_RUN_KEY = "report_last_run"
WEEKDAY_NAMES = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


def default_schedule() -> dict:
    """缺省计划：关闭，周一 09:00 UTC。

    Returns:
        dict: {enabled, weekday, hour}。
    """
    return {"enabled": False, "weekday": 0, "hour": 9}


async def load_schedule(db: AsyncSession) -> dict:
    """读计划（缺省合并 + 越界钳制）。

    Args:
        db (AsyncSession): 会话。

    Returns:
        dict: {enabled, weekday(0-6, 0=周一), hour(0-23)}。
    """
    row = await db.get(SystemSetting, SCHEDULE_KEY)
    cfg = default_schedule()
    if row and isinstance(row.value, dict):
        cfg.update({k: v for k, v in row.value.items() if k in cfg})
    cfg["weekday"] = max(0, min(6, int(cfg["weekday"])))
    cfg["hour"] = max(0, min(23, int(cfg["hour"])))
    return cfg


async def save_schedule(db: AsyncSession, cfg: dict) -> dict:
    """保存计划（写路径；调用方若直调需自行 commit，API 层由 get_db 提交）。

    Args:
        db (AsyncSession): 会话。
        cfg (dict): {enabled, weekday, hour}。

    Returns:
        dict: 保存后的计划。
    """
    row = await db.get(SystemSetting, SCHEDULE_KEY)
    if row:
        row.value = cfg
    else:
        db.add(SystemSetting(key=SCHEDULE_KEY, value=cfg, description="周报推送计划"))
    await db.flush()
    return cfg


async def last_run_date(db: AsyncSession) -> str:
    """上次运行日期（YYYY-MM-DD；未跑过为空串）。"""
    row = await db.get(SystemSetting, LAST_RUN_KEY)
    return str(row.value) if row and row.value else ""


async def set_last_run_date(db: AsyncSession, day: str) -> None:
    """记录运行日期（周去重锚点）。flush 不 commit（同 save 约定）。"""
    row = await db.get(SystemSetting, LAST_RUN_KEY)
    if row:
        row.value = day
    else:
        db.add(SystemSetting(key=LAST_RUN_KEY, value=day, description="周报上次运行日期"))
    await db.flush()


def due(cfg: dict, now: datetime, last_run: str) -> bool:
    """命中判定：enabled ∧ 星期 ∧ 小时 ∧ 本周未跑（日期去重）。"""
    today = now.strftime("%Y-%m-%d")
    return (
        bool(cfg.get("enabled"))
        and now.weekday() == cfg["weekday"]
        and now.hour == cfg["hour"]
        and last_run != today
    )


async def build_digest(db: AsyncSession, now: datetime | None = None) -> str:
    """汇总 7 天数据生成摘要文本（多行，渠道正文直用）。

    Args:
        db (AsyncSession): 会话。
        now (datetime | None): 基准时刻（默认当前 UTC）。

    Returns:
        str: 多行摘要（NAS 周报标题 + 分节要点）。
    """
    now = now or datetime.now(UTC)
    since = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")

    fired = (
        await db.execute(select(func.count()).select_from(AlertEvent).where(AlertEvent.fired_at >= since))
    ).scalar() or 0
    firing_now = (
        await db.execute(select(func.count()).select_from(AlertEvent).where(AlertEvent.status == "firing"))
    ).scalar() or 0
    max_temp = (
        await db.execute(select(func.max(MetricPoint.temp_max)).where(MetricPoint.ts >= since))
    ).scalar()

    lines = [
        f"NAS 周报（{now.strftime('%Y-%m-%d')}）",
        f"· 近 7 天告警事件 {fired} 次，当前活跃 {firing_now} 条",
        f"· 近 7 天最高温 {max_temp:g} °C" if max_temp is not None else "· 近 7 天无温度采样",
    ]

    forecasts = {f["mount"]: f for f in await capacity.forecast_all(db)}
    vol_lines = []
    for mount, f in sorted(forecasts.items()):
        if f["days_to_full"] is None:
            vol_lines.append(f"    {mount}: 已用 {f['last_percent']}%（增速≈0）")
        else:
            vol_lines.append(f"    {mount}: 已用 {f['last_percent']}%，按当前增速约 {f['days_to_full']:g} 天写满")
    if vol_lines:
        lines.append("· 容量预测：" + ("\n".join(vol_lines[0:6]) if vol_lines else ""))

    # 磁盘健康分布（smart_15m 最近一天 1d 桶：reallocated 有增量的盘单列）
    from app.services.storage import smart_history

    deltas = await smart_history.rate_deltas(db, "reallocated")
    growing = [d for d in deltas if d["delta"] > 0]
    if growing:
        lines.append("· SMART 重映射扇区 7 天增长：" + "、".join(f"{d['device']} +{d['delta']:g}" for d in growing))
    else:
        lines.append("· SMART：各盘重映射扇区 7 天无增长")
    return "\n".join(lines)


async def push_now(db: AsyncSession) -> str:
    """立即生成周报并广播（手动发送与定时触发共用）。

    Args:
        db (AsyncSession): 会话（调用方 commit）。

    Returns:
        str: 摘要文本。
    """
    from app.services.alert import engine as alert_engine

    digest = await build_digest(db)
    await alert_engine.notify_broadcast(db, title="NAS 周报", body=digest)
    return digest


async def schedule_tick(db: AsyncSession, now: datetime | None = None) -> bool:
    """10 分钟拍：命中计划窗口且未跑 → 广播周报并记运行日期。

    Args:
        db (AsyncSession): 任务级会话（本函数自行 commit）。
        now (datetime | None): 基准时刻。

    Returns:
        bool: 本拍是否触发。
    """
    now = now or datetime.now(UTC)
    cfg = await load_schedule(db)
    if not due(cfg, now, await last_run_date(db)):
        return False
    await set_last_run_date(db, now.strftime("%Y-%m-%d"))
    await push_now(db)
    await db.commit()
    from app.services.alert import engine as alert_engine

    alert_engine.schedule_drain()
    return True
