"""一键体检（花活二期 N）：纯聚合零新增采集——读现成服务出六维体检项 + 总分。

聚合面：硬盘预言（J 评分）/ 容量预测（capacity）/ 阵列状态（raid）/
温度余量（temperature）/ 30 天告警（alert_events 统计）/ 端口暴露面
（psutil LISTEN，仅计数与 0.0.0.0/:: 暴露占比，不列进程详情）。
只读不出网；单项拿不到数据为 warn 缺省，不造假分。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import psutil
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import AlertEvent
from app.services.monitor import temperature
from app.services.storage import capacity, raid as raid_service, smart_history, smart_oracle
from app.services.storage import volumes as volume_service

# 各体检项权重（总分 = Σ 维度分 × 权重，缺失维度剔除后重归一）
_WEIGHTS = {"oracle": 0.25, "capacity": 0.15, "raid": 0.2, "temp": 0.15, "alerts": 0.15, "ports": 0.1}
ITEM_KEYS = tuple(_WEIGHTS)

# 容量写满 / 触阈值倒计时的 warn 线（天）
_CAPACITY_WARN_DAYS = 30
# 温度余量：max 温度到 60 °C 的余量折算（25 °C 余量满分，与 oracle temp 维度同口径）
_TEMP_HOT = 60.0
_TEMP_SPAN = 25.0


def _grade_of(score: float) -> str:
    """维度分 → 等级（与 oracle grade 同门槛）。"""
    return "ok" if score >= 85 else "warn" if score >= 60 else "bad"


async def run_checkup(db: AsyncSession, now: datetime | None = None) -> dict:
    """执行体检，返回 {items: [{key, status, score, detail}], score, grade}。

    Args:
        db (AsyncSession): 只读会话。
        now (datetime | None): 告警统计窗口基准；None 取当前 UTC。

    Returns:
        dict: items 六项（key 顺序见 ITEM_KEYS）；score 为加权总分（全缺时 None）；
            grade 同 oracle 门槛（ok/warn/bad）。
    """
    now = now or datetime.now(UTC)
    items: list[dict] = []

    # 1) 硬盘预言：全部盘 oracle 最低分（无盘/无采样按缺数据 warn 处理）
    try:
        disks = await volume_service.list_disks()
    except Exception:  # noqa: BLE001 单项失败降级为缺数据
        disks = []
    oracle_map = await smart_oracle.forecast_all(
        db, [smart_history.smart_key(d.get("device") or "") for d in disks]
    )
    scores = [o["score"] for o in oracle_map.values() if o.get("score") is not None]
    if scores:
        worst = min(scores)
        bad_n = sum(1 for s in scores if s < 60)
        watch_n = sum(1 for s in scores if 60 <= s < 85)
        oracle_score = float(worst)
        detail = f"最低 {worst} 分"
        if bad_n:
            detail += f" · {bad_n} 盘异常"
        elif watch_n:
            detail += f" · {watch_n} 盘观察"
    else:
        oracle_score, detail = None, "暂无盘评分（—）"
    items.append(_item("oracle", oracle_score, detail))

    # 2) 容量预测：最近写满日（有增速的挂载点里最小 days_to_full）
    try:
        forecasts = await capacity.forecast_all(db, now=now)
    except Exception:  # noqa: BLE001
        forecasts = []
    days = [f["days_to_full"] for f in forecasts if f.get("days_to_full") is not None]
    if days:
        nearest = min(days)
        cap_score = 100.0 if nearest > 90 else (60.0 if nearest > _CAPACITY_WARN_DAYS else 20.0)
        detail = f"最近写满约 {nearest:.0f} 天"
    else:
        cap_score, detail = None, "暂无写满预测（—）"
    items.append(_item("capacity", cap_score, detail))

    # 3) 阵列状态：软/硬阵列降级计数（storcli 失败不阻断）
    try:
        raid = await raid_service.raid_status()
    except Exception:  # noqa: BLE001
        raid = {}
    vols = [*(raid.get("hardware_raid") or []), *(raid.get("software_raid") or [])]
    degraded = sum(1 for v in vols if not v.get("healthy"))
    failed_drives = sum(1 for d in raid.get("drives") or [] if d.get("failed") or d.get("faulty"))
    if vols or raid.get("drives"):
        raid_score = 0.0 if (degraded or failed_drives) else 100.0
        detail = (
            f"{len(vols)} 阵列 · {failed_drives} 故障盘" if (degraded or failed_drives) else f"{len(vols)} 阵列全部健康"
        )
    else:
        raid_score, detail = 100.0, "无阵列（直连盘）"
    items.append(_item("raid", raid_score, detail))

    # 4) 温度余量：全传感器最高温（60s 缓存，零新增 fork）
    try:
        temps = await temperature.temperatures()
        temp_max = temperature.max_celsius(temps)
    except Exception:  # noqa: BLE001
        temp_max = None
    if temp_max is not None:
        temp_score = max(0.0, min(100.0, (_TEMP_HOT - temp_max) / _TEMP_SPAN * 100))
        detail = f"最高 {temp_max:.0f} °C"
    else:
        temp_score, detail = None, "无温度数据源（—）"
    items.append(_item("temp", temp_score, detail))

    # 5) 30 天告警：critical×10 + warning×3 扣分（resolved 一并计，反映近期稳定性）
    since = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S")
    result = await db.execute(
        select(AlertEvent.severity, func.count()).where(AlertEvent.fired_at >= since).group_by(AlertEvent.severity)
    )
    counts = {sev: n for sev, n in result.all()}
    crit_n = counts.get("critical", 0)
    warn_n = counts.get("warning", 0)
    total30 = sum(counts.values())
    alert_score = max(0.0, 100.0 - crit_n * 10 - warn_n * 3)
    detail = f"30 天 {total30} 条（{crit_n} 严重 / {warn_n} 警告）" if total30 else "30 天无告警"
    items.append(_item("alerts", alert_score, detail))

    # 6) 端口暴露面：LISTEN 总数 + 非回环绑定占比（只计数，不列进程）
    try:
        listens = [
            c for c in psutil.net_connections(kind="inet") if c.status == psutil.CONN_LISTEN
        ]
    except Exception:  # noqa: BLE001
        listens = []
    if listens:
        exposed = sum(1 for c in listens if c.laddr and c.laddr.ip in ("0.0.0.0", "::"))
        port_score = max(0.0, 100.0 - exposed * 4)
        detail = f"监听 {len(listens)} 口 · 对外暴露 {exposed}"
    else:
        port_score, detail = None, "无监听端口（—）"
    items.append(_item("ports", port_score, detail))

    known = [i for i in items if i["score"] is not None]
    total_w = sum(_WEIGHTS[i["key"]] for i in known)
    score = round(sum((i["score"] or 0) * _WEIGHTS[i["key"]] for i in known) / total_w) if total_w else None
    return {"items": items, "score": score, "grade": _grade_of(score) if score is not None else None}


def _item(key: str, score: float | None, detail: str) -> dict:
    """单项装配：分数缺省时状态 warn（缺数据不是健康，但也不算故障）。"""
    return {
        "key": key,
        "score": round(score, 1) if score is not None else None,
        "status": _grade_of(score) if score is not None else "warn",
        "detail": detail,
    }
