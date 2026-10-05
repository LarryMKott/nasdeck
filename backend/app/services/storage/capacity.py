"""容量趋势与写满预测：15m 采样 → 1h 桶，14 天最小二乘回归 → days_to_full。

增速按"已用百分比"回归（used/total），卷扩容后历史百分比自然衔接，不受总量变更影响；
增速≈0（水平回归）返回 days_to_full=None——"无增速"是合法真值，前端显式"—"。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage import VolumePoint

# 回归窗口与保留窗：14 天回归（容量增长缓慢，短窗噪声大），1h 桶保留 90 天
REGRESSION_DAYS = 14
KEEP_DAYS = 90
# 最小采样跨度（小时）：低于此值两点贴太近，斜率全是噪声
_MIN_SPAN_HOURS = 6


def _hour_bucket(now: datetime) -> str:
    return now.strftime("%Y-%m-%dT%H:00:00")


async def record_snapshots(db: AsyncSession, volumes: list[dict], now: datetime | None = None) -> int:
    """整桶覆盖写 1h 容量点，返回写入行数。删除限定本批挂载点（单卷缺席不放大）。"""
    now = now or datetime.now(UTC)
    key = _hour_bucket(now)
    rows = [
        VolumePoint(
            ts=key,
            mount=v["mount"],
            used_gb=round(v["used_bytes"] / 1024 ** 3, 3),
            total_gb=round(v["total_bytes"] / 1024 ** 3, 3),
        )
        for v in volumes
        if v.get("mount") and v.get("total_bytes")
    ]
    if not rows:
        return 0
    mounts = {r.mount for r in rows}
    await db.execute(delete(VolumePoint).where(VolumePoint.ts == key, VolumePoint.mount.in_(mounts)))
    db.add_all(rows)
    await db.flush()
    return len(rows)


async def prune_old(db: AsyncSession, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    cutoff = (now - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%dT%H:%M:%S")
    result = await db.execute(delete(VolumePoint).where(VolumePoint.ts < cutoff))
    return result.rowcount or 0


def _slope_percent_per_day(points: list[tuple[datetime, float]]) -> float | None:
    """最小二乘斜率（百分比/天）。跨度不足返回 None（采样太近全是噪声）。"""
    t0 = points[0][0]
    xs = [(dt - t0).total_seconds() / 86400 for dt, _ in points]
    ys = [pct for _, pct in points]
    if xs[-1] < _MIN_SPAN_HOURS / 24:
        return None
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    if sxx <= 0:
        return None
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    return sxy / sxx


async def forecast_all(db: AsyncSession, now: datetime | None = None) -> list[dict]:
    """各挂载点写满预测：[{mount, days_to_full, slope_percent_per_day, last_percent, sampled_hours}]。

    days_to_full=None 表示有数据但增速≈0（回归斜率 ≤0 或跨度不足）；
    挂载点无采样记录则不出现在返回值中。
    """
    now = now or datetime.now(UTC)
    since = _hour_bucket(now - timedelta(days=REGRESSION_DAYS))
    result = await db.execute(
        select(VolumePoint.mount, VolumePoint.ts, VolumePoint.used_gb, VolumePoint.total_gb)
        .where(VolumePoint.ts >= since)
        .order_by(VolumePoint.mount, VolumePoint.ts)
    )
    series: dict[str, list[tuple[datetime, float, float, float]]] = {}
    for mount, ts, used_gb, total_gb in result.all():
        try:
            dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=UTC)
        except ValueError:
            continue
        pct = used_gb / total_gb * 100 if total_gb > 0 else 0.0
        series.setdefault(mount, []).append((dt, pct, used_gb, total_gb))

    out = []
    for mount, points in series.items():
        slope = _slope_percent_per_day([(dt, pct) for dt, pct, _u, _t in points])
        last_pct = points[-1][1]
        days_to_full = None
        if slope is not None and slope > 0:
            days_to_full = round(max(0.0, (100 - last_pct) / slope), 1)
        out.append(
            {
                "mount": mount,
                "days_to_full": days_to_full,
                # 斜率保留 4 位：一天涨 0.1% 量级的慢增速也要可判
                "slope_percent_per_day": round(slope, 4) if slope is not None else 0.0,
                "last_percent": round(last_pct, 1),
                "sampled_hours": len(points),
            }
        )
    return out
