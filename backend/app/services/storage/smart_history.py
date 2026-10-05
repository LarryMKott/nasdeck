"""SMART 趋势历史：15m 采样 → 1h/1d 两级桶（SMART 变化慢，独立于 metric_points）。

同桶重复采样整桶覆盖（最新值胜出），无聚合任务；桶键为 UTC 墙钟串（契约 §1.5）。
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage import SmartPoint

# 关键指标白名单：ATA 按 attribute id 取 raw 前导数字，NVMe 取健康日志字段。
# temp_c / power_on_hours 直取 smart_report 顶层（两形态通用）。
_ATA_METRICS = {5: "reallocated", 197: "pending", 198: "uncorrectable", 177: "wear_leveling"}
_NVME_METRICS = {"nvme_percent_used": "percent_used", "nvme_media_errors": "media_errors"}

TRACKED_METRICS = (
    "reallocated",
    "pending",
    "uncorrectable",
    "wear_leveling",
    "percent_used",
    "media_errors",
    "temp_c",
    "power_on_hours",
)

# 保留窗口：1h 桶 90 天（7/30 天趋势查询），1d 桶 730 天（长周期健康档案）
KEEP_1H_DAYS = 90
KEEP_1D_DAYS = 730

# smart_rate 速率规则的评估窗口（天）
RATE_WINDOW_DAYS = 7


def smart_key(device: str) -> str:
    """lsblk 盘名 → SMART 探测键：sda 原样；nvme0n1 回退控制器名 nvme0（与盘温/健康同键）。

    Args:
        device (str): lsblk 盘名。

    Returns:
        str: SMART 探测键。
    """
    return re.sub(r"n\d+$", "", device) if device.startswith("nvme") else device


def extract_metrics(report: dict) -> dict[str, tuple[float, str | None]]:
    """从 smart_report 提取关键指标。

    Args:
        report (dict): smart_report 输出。

    Returns:
        dict[str, tuple[float, str | None]]: {metric: (value, raw_text)}；
            休眠盘 attributes 为空返回 {}（不记录）。
    """
    out: dict[str, tuple[float, str | None]] = {}
    for attr in report.get("attributes") or []:
        name = _ATA_METRICS.get(attr.get("id"))
        if not name:
            continue
        m = re.match(r"-?\d+", str(attr.get("raw") or ""))
        if m:
            out[name] = (float(m.group()), str(attr.get("raw")))
    if report.get("nvme_percent_used") is not None:
        out["percent_used"] = (float(report["nvme_percent_used"]), None)
    if report.get("nvme_media_errors") is not None:
        out["media_errors"] = (float(report["nvme_media_errors"]), None)
    if report.get("temp_c") is not None:
        out["temp_c"] = (float(report["temp_c"]), None)
    if report.get("power_on_hours") is not None:
        out["power_on_hours"] = (float(report["power_on_hours"]), None)
    return out


def _hour_bucket(now: datetime) -> str:
    """生成整点桶键（UTC 墙钟串，口径同 MetricPoint，契约 §1.5）。

    Args:
        now (datetime): 桶键基准时刻。

    Returns:
        str: 形如 ``YYYY-MM-DDTHH:00:00`` 的桶键。
    """
    return now.strftime("%Y-%m-%dT%H:00:00")


def _day_bucket(now: datetime) -> str:
    """生成当日 00:00 桶键（1d 粒度；窗口截断必须按整日，按时刻截会丢边界日）。

    Args:
        now (datetime): 桶键基准时刻。

    Returns:
        str: 形如 ``YYYY-MM-DDT00:00:00`` 的桶键。
    """
    return now.strftime("%Y-%m-%dT00:00:00")


async def record_snapshots(db: AsyncSession, reports: list[dict], now: datetime | None = None) -> int:
    """整桶覆盖写 1h/1d 点，返回写入行数。

    休眠盘（attributes 空）自然跳过。

    Args:
        db (AsyncSession): 调用方会话（本函数只 flush，commit 归调用方）。
        reports (list[dict]): smart_report 输出列表。
        now (datetime | None): 桶键基准时刻；None 取当前 UTC。

    Returns:
        int: 写入行数。
    """
    now = now or datetime.now(UTC)
    hour, day = _hour_bucket(now), _day_bucket(now)
    rows: list[SmartPoint] = []
    for report in reports:
        device = report.get("device")
        if not device:
            continue
        for metric, (value, raw_text) in extract_metrics(report).items():
            rows.append(
                SmartPoint(ts=hour, granularity="1h", device=device, metric=metric, value=value, raw_text=raw_text)
            )
            rows.append(
                SmartPoint(ts=day, granularity="1d", device=device, metric=metric, value=value, raw_text=raw_text)
            )
    if not rows:
        return 0
    # 最新值胜出：当前桶删旧插新。删除限定在本批设备——单盘采集失败缺席本批时，
    # 不得连带清掉其它盘本桶已落的历史（delete 全桶会放大单盘故障）
    devices = {r.device for r in rows}
    for gran, key in (("1h", hour), ("1d", day)):
        await db.execute(
            delete(SmartPoint).where(
                SmartPoint.granularity == gran,
                SmartPoint.ts == key,
                SmartPoint.device.in_(devices),
            )
        )
    db.add_all(rows)
    await db.flush()
    return len(rows)


async def prune_old(db: AsyncSession, now: datetime | None = None) -> int:
    """删除超保留窗的 SMART 点，返回删除行数。

    由采集任务每日触发一次。

    Args:
        db (AsyncSession): 调用方会话。
        now (datetime | None): 保留截止线基准时刻；None 取当前 UTC。

    Returns:
        int: 删除行数（1h/1d 两级桶合计）。
    """
    now = now or datetime.now(UTC)
    total = 0
    for gran, keep_days in (("1h", KEEP_1H_DAYS), ("1d", KEEP_1D_DAYS)):
        cutoff = (now - timedelta(days=keep_days)).strftime("%Y-%m-%dT%H:%M:%S")
        result = await db.execute(delete(SmartPoint).where(SmartPoint.granularity == gran, SmartPoint.ts < cutoff))
        total += result.rowcount or 0
    return total


async def trend_series(db: AsyncSession, device: str, metric: str, days: int = 30) -> dict:
    """查询单盘单指标趋势序列。

    1h 桶截断到时刻，1d 桶截断到整日（桶键是 T00:00:00，按时刻截会丢边界日）。

    Args:
        db (AsyncSession): 只读会话。
        device (str): 盘名（SMART 探测键，经 smart_key 归一）。
        metric (str): 指标名（TRACKED_METRICS 之一）。
        days (int): 回看窗口天数；≤30 用 1h 桶，更长用 1d 桶。

    Returns:
        dict: {device, metric, granularity, days, points}，points 按 ts 升序，
            每点 {ts, value, raw_text}。
    """
    granularity = "1h" if days <= 30 else "1d"
    since = datetime.now(UTC) - timedelta(days=days)
    cutoff = (since.strftime("%Y-%m-%dT%H:%M:%S") if granularity == "1h" else _day_bucket(since))
    result = await db.execute(
        select(SmartPoint.ts, SmartPoint.value, SmartPoint.raw_text)
        .where(
            SmartPoint.granularity == granularity,
            SmartPoint.device == device,
            SmartPoint.metric == metric,
            SmartPoint.ts >= cutoff,
        )
        .order_by(SmartPoint.ts)
    )
    points = [{"ts": r[0], "value": r[1], "raw_text": r[2]} for r in result.all()]
    return {"device": device, "metric": metric, "granularity": granularity, "days": days, "points": points}


async def rate_deltas(db: AsyncSession, metric: str, days: int = RATE_WINDOW_DAYS) -> list[dict]:
    """计算各盘 metric 在 days 窗口的增量（1d 桶，窗口内首末点）。

    新盘（窗口内不足两点）不产生增量——避免把"刚接入"误判为"突变"。
    窗口截断到整日：1d 桶键是 T00:00:00，按时刻截会把边界日的桶整段截掉。

    Args:
        db (AsyncSession): 只读会话。
        metric (str): 指标名（TRACKED_METRICS 之一）。
        days (int): 评估窗口天数（smart_rate 速率规则默认 RATE_WINDOW_DAYS）。

    Returns:
        list[dict]: 每盘 {device, old, new, delta}（delta 保留 4 位小数）。
    """
    since = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00")
    result = await db.execute(
        select(SmartPoint.device, SmartPoint.ts, SmartPoint.value)
        .where(SmartPoint.granularity == "1d", SmartPoint.metric == metric, SmartPoint.ts >= since)
        .order_by(SmartPoint.device, SmartPoint.ts)
    )
    series: dict[str, list[tuple[str, float]]] = {}
    for device, ts, value in result.all():
        series.setdefault(device, []).append((ts, value))
    out = []
    for device, points in series.items():
        if len(points) < 2:
            continue
        old, new = points[0][1], points[-1][1]
        out.append({"device": device, "old": old, "new": new, "delta": round(new - old, 4)})
    return out
