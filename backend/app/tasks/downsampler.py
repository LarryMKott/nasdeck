"""历史数据降采样：raw → 1m 聚合（超保留期），1m → 10m 聚合，1m 超 30 天删除。

桶键一律按 UTC 计算（ts 本就是 UTC 墙钟串，契约 §1.5），不得用 naive
datetime.timestamp()——那会按宿主机本地时区解释，非 UTC 机器上整体漂移。
"""

from __future__ import annotations

import calendar
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import session_factory
from app.models.metrics import MetricPoint
from app.models.system import SystemSetting

logger = logging.getLogger(__name__)

# 一次性迁移标记：v1 降采样存在 1m 桶长误用 60min、桶键按本地时区漂移两处缺陷，
# 产生的聚合行整体失真且无法换算。升级后清除全部非 raw 聚合，由 raw 保留窗口
# （raw_keep_minutes）起重新积累。标记落 system_settings，避免每次重启重复清除。
_MIGRATION_KEY = "downsample_v2_migrated"


async def downsample_tick() -> None:
    try:
        async with session_factory() as db:
            cutoff = _iso_minutes_ago(settings.raw_keep_minutes)
            await _aggregate(db, "raw", "1m", 1, cutoff)
            await db.execute(delete(MetricPoint).where(MetricPoint.granularity == "raw", MetricPoint.ts < cutoff))
            await _aggregate(db, "1m", "10m", 10, _iso_minutes_ago(7 * 24 * 60))
            await db.execute(
                delete(MetricPoint).where(
                    MetricPoint.granularity == "1m", MetricPoint.ts < _iso_minutes_ago(30 * 24 * 60)
                )
            )
            # 10m 点同样要有终点（查询最大区间 30 天，留 90 天余量），否则常年运行 DB 无限膨胀
            await db.execute(
                delete(MetricPoint).where(
                    MetricPoint.granularity == "10m", MetricPoint.ts < _iso_minutes_ago(90 * 24 * 60)
                )
            )
            await _prune_hardware_items(db)
            await db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("downsample 异常: %s", exc)


async def _prune_hardware_items(db: AsyncSession) -> None:
    """硬件清单快照只保留最近窗口：hardware API 只读每 kind 最新一条，
    slow tick 每分钟一轮（6 kind/轮），20 分钟窗口 = ~120 行恒定规模。"""
    from app.models.hardware import HardwareItem

    cutoff = (datetime.now(UTC) - timedelta(minutes=20)).strftime("%Y-%m-%d %H:%M:%S")
    await db.execute(delete(HardwareItem).where(HardwareItem.created_at < cutoff))


async def purge_legacy_aggregates() -> None:
    """升级后一次性清除 v1 失真聚合行（幂等，已迁移则跳过）。"""
    async with session_factory() as db:
        if await db.get(SystemSetting, _MIGRATION_KEY) is not None:
            return
        result = await db.execute(delete(MetricPoint).where(MetricPoint.granularity != "raw"))
        db.add(SystemSetting(key=_MIGRATION_KEY, value=True))
        await db.commit()
        logger.warning(
            "已清除 %s 行失真历史聚合（v1 降采样桶长/时区缺陷），历史将从现在起重新积累",
            result.rowcount,
        )


def _iso_minutes_ago(minutes: int) -> str:
    return (datetime.now(UTC) - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S")


def _bucket_key(ts: str, bucket_minutes: int) -> str | None:
    """UTC 墙钟串 → 对齐到桶起点的桶键。非 ISO 格式返回 None（跳过）。"""
    try:
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None
    # timegm 显式按 UTC 解释，与宿主机本地时区无关（naive .timestamp() 会漂移）
    epoch = calendar.timegm(dt.timetuple()) // (bucket_minutes * 60) * bucket_minutes * 60
    return datetime.fromtimestamp(epoch, UTC).strftime("%Y-%m-%dT%H:%M:%S")


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
        key = _bucket_key(ts, bucket_minutes)
        if key is not None:
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
                    func.avg(MetricPoint.disk_read_kbps), func.avg(MetricPoint.disk_write_kbps),
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
                disk_read_kbps=round(rows[5], 1) if rows[5] is not None else None,
                disk_write_kbps=round(rows[6], 1) if rows[6] is not None else None,
            )
        )
    await db.flush()
