"""历史数据降采样：raw → 1m 聚合（超保留期），1m 超 30 天删除。"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import session_factory
from app.models.metrics import MetricPoint

logger = logging.getLogger(__name__)


async def downsample_tick() -> None:
    try:
        async with session_factory() as db:
            cutoff = _iso_minutes_ago(settings.raw_keep_minutes)
            await _aggregate(db, "raw", "1m", 60, cutoff)
            await db.execute(delete(MetricPoint).where(MetricPoint.granularity == "raw", MetricPoint.ts < cutoff))
            await _aggregate(db, "1m", "10m", 10, _iso_minutes_ago(7 * 24 * 60))
            await db.execute(
                delete(MetricPoint).where(
                    MetricPoint.granularity == "1m", MetricPoint.ts < _iso_minutes_ago(30 * 24 * 60)
                )
            )
            await db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("downsample 异常: %s", exc)


def _iso_minutes_ago(minutes: int) -> str:
    return (datetime.now(UTC) - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S")


async def _aggregate(db: AsyncSession, from_g: str, to_g: str, bucket_minutes: int, since: str) -> None:
    """按时间桶聚合（cpu/内存/网络均值，温度取最大）——SQLite 端做轻量聚合。"""
    from sqlalchemy import func

    result = await db.execute(
        select(MetricPoint.ts)
        .where(MetricPoint.granularity == from_g, MetricPoint.ts >= since)
        .order_by(MetricPoint.ts)
    )
    tss = [r[0] for r in result.all()]
    if not tss:
        return
    buckets: dict[str, list[str]] = {}
    for ts in tss:
        try:
            dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            continue
        epoch = int(dt.timestamp()) // (bucket_minutes * 60) * bucket_minutes * 60
        key = datetime.fromtimestamp(epoch, UTC).strftime("%Y-%m-%dT%H:%M:%S")
        buckets.setdefault(key, []).append(ts)

    existing = await db.execute(
        select(MetricPoint.ts).where(MetricPoint.granularity == to_g, MetricPoint.ts.in_(list(buckets)))
    )
    have = {r[0] for r in existing.all()}

    for key, members in buckets.items():
        if key in have:
            continue
        rows = (
            await db.execute(
                select(
                    func.avg(MetricPoint.cpu), func.avg(MetricPoint.mem_mb), func.avg(MetricPoint.net_kbps),
                    func.max(MetricPoint.temp_max), func.max(MetricPoint.gpu),
                ).where(MetricPoint.granularity == from_g, MetricPoint.ts.in_(members))
            )
        ).one()
        db.add(
            MetricPoint(
                ts=key,
                granularity=to_g,
                cpu=round(rows[0], 2) if rows[0] is not None else None,
                mem_mb=round(rows[1], 1) if rows[1] is not None else None,
                net_kbps=round(rows[2], 1) if rows[2] is not None else None,
                temp_max=rows[3],
                gpu=rows[4],
            )
        )
    await db.flush()
