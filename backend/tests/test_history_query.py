"""query_history 粒度选择与时间桶降采样：窗口参数必须真实生效（回归 2026-09-30）。

此前实现固定取最近 N 条 raw 行，minutes 参数无效——24h 窗口实际只覆盖 ~N 秒，
前端图表全窗口恒为 2-3 分钟。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.db.session import session_factory
from app.services.monitor.history import query_history

FMT = "%Y-%m-%dT%H:%M:%S"


async def _seed_raw(count: int, step_seconds: int, cpu: float = 7.5) -> datetime:
    """在真实“现在”往前铺等间隔 raw 行（ts 与 query_history 的 since 同一 UTC 口径）。

    先清空 raw 保留期内的行：session 级共享库，多个测试/文件都在“当前时刻”附近
    播种真实时间戳行，残留行会混进被测窗口（这些测试都先于我的文件跑完或自带
    2030 前缀时间戳，删除不影响它们）。
    """
    from sqlalchemy import delete

    from app.models.metrics import MetricPoint

    newest = datetime.now(UTC).replace(microsecond=0)
    horizon = (newest - timedelta(minutes=120)).strftime(FMT)
    tss = [(newest - timedelta(seconds=i * step_seconds)).strftime(FMT) for i in range(count)]
    async with session_factory() as db:
        await db.execute(delete(MetricPoint).where(MetricPoint.granularity == "raw", MetricPoint.ts >= horizon))
        db.add_all(
            MetricPoint(
                ts=ts,
                granularity="raw",
                cpu=cpu,
                mem_mb=1000.0,
                net_kbps=float(i),
            )
            for i, ts in enumerate(tss)
        )
        await db.commit()
    return newest


def _ts(point: dict) -> datetime:
    return datetime.strptime(point["ts"], FMT).replace(tzinfo=UTC)


@pytest.mark.asyncio
async def test_raw_window_buckets_span_whole_window(client):
    """raw 窗口内点数超 points：按时间桶均分，首尾铺满请求窗口而不是最近几点。

    30s 间隔 × 200 行 = 100 分钟跨度；请求最近 90 分钟 → 窗口内约 180 行、
    5400s/60 点 = 90s 桶。旧实现此处只会返回最近 60 行（30 分钟）。
    """
    newest = await _seed_raw(200, step_seconds=30)
    since = newest - timedelta(seconds=90 * 60)
    async with session_factory() as db:
        points, granularity = await query_history(db, minutes=90, points=60)
    assert granularity == "raw"
    assert 0 < len(points) <= 61  # 桶均分 + 首尾半桶余量
    assert _ts(points[0]) <= since + timedelta(seconds=90)  # 窗口起点有覆盖
    assert _ts(points[-1]) >= newest - timedelta(seconds=90)  # 窗口终点贴到当前


@pytest.mark.asyncio
async def test_few_points_bypass_bucketing(client):
    """点数不超 points：原样返回，不做桶聚合。"""
    await _seed_raw(30, step_seconds=1)
    async with session_factory() as db:
        points, granularity = await query_history(db, minutes=2, points=500)
    assert granularity == "raw"
    assert len(points) == 30
    assert points[0]["cpu_max"] == 7.5


@pytest.mark.asyncio
async def test_bucket_values_are_averages(client):
    """桶值是均值：等值序列聚合后 cpu_avg 保持原值。"""
    await _seed_raw(120, step_seconds=1)
    async with session_factory() as db:
        points, _ = await query_history(db, minutes=2, points=60)
    assert points
    assert all(p["cpu_avg"] == pytest.approx(7.5) for p in points)


@pytest.mark.asyncio
async def test_long_window_unions_older_granularity_and_raw(client):
    """窗口超 raw 保留期：老区段取 1m、最近保留期取 raw，两段按时间升序拼接不重叠。"""
    from sqlalchemy import delete

    from app.models.metrics import MetricPoint

    newest = await _seed_raw(60, step_seconds=1)
    raw_since = newest - timedelta(minutes=120)
    older_ts = [(newest - timedelta(minutes=m)).strftime(FMT) for m in (300, 240, 180)]
    async with session_factory() as db:
        await db.execute(delete(MetricPoint).where(MetricPoint.granularity == "1m"))
        db.add_all(MetricPoint(ts=ts, granularity="1m", cpu=3.0, mem_mb=900.0, net_kbps=50.0) for ts in older_ts)
        await db.commit()
    async with session_factory() as db:
        points, granularity = await query_history(db, minutes=1440, points=144)
    assert granularity == "1m"
    assert len(points) > 3  # 1m 段 + raw 段都有
    tss = [_ts(p) for p in points]
    assert tss == sorted(tss)  # 升序
    assert tss[0] == datetime.strptime(older_ts[0], FMT).replace(tzinfo=UTC)  # 1m 段在最前
    assert tss[-1] >= raw_since - timedelta(seconds=90)  # raw 段贴到当前
    assert all(_ts(p) < raw_since for p in points if p["granularity"] == "1m")  # 按 raw 起点切分


@pytest.mark.asyncio
async def test_long_window_selects_1m_granularity(client):
    """窗口超 raw 保留期（settings.raw_keep_minutes=120）：选 1m 粒度。"""
    async with session_factory() as db:
        _, granularity = await query_history(db, minutes=121, points=144)
    assert granularity == "1m"


@pytest.mark.asyncio
async def test_week_window_selects_10m_granularity(client):
    """窗口超 7 天：选 10m 粒度。"""
    async with session_factory() as db:
        _, granularity = await query_history(db, minutes=8 * 24 * 60, points=168)
    assert granularity == "10m"
