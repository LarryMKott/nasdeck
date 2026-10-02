"""降采样回归测试：桶对齐、UTC 桶键、桶长（v1 双缺陷回归锁）与一次性迁移。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.metrics import MetricPoint
from app.tasks import downsampler


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


def test_bucket_key_aligns_and_handles_garbage():
    assert downsampler._bucket_key("2026-10-01T12:00:37", 1) == "2026-10-01T12:00:00"
    assert downsampler._bucket_key("2026-10-01T12:07:21", 10) == "2026-10-01T12:00:00"
    assert downsampler._bucket_key("2026-10-01T12:17:21", 10) == "2026-10-01T12:10:00"
    assert downsampler._bucket_key("garbage", 1) is None


def test_bucket_key_is_utc_regardless_of_local_timezone():
    # 桶键必须由 UTC 换算（timegm 口径）；v1 用 naive .timestamp() 时在非 UTC
    # 宿主机上 12:00 UTC 会漂成 04:00——本断言与 timegm 直接对拍锁死该行为
    assert downsampler._bucket_key("2026-10-01T12:00:00", 60) == "2026-10-01T12:00:00"
    assert downsampler._bucket_key("2026-10-01T23:59:59", 60) == "2026-10-01T23:00:00"
    assert downsampler._bucket_key("2026-10-01T00:00:00", 60) == "2026-10-01T00:00:00"


async def test_aggregate_raw_to_1m_minute_buckets(db):
    # 同一分钟内两点取均值，跨分钟各自成桶
    for ts, cpu in [("2026-10-01T12:00:00", 10.0), ("2026-10-01T12:00:30", 30.0), ("2026-10-01T12:01:00", 50.0)]:
        db.add(MetricPoint(ts=ts, granularity="raw", cpu=cpu))
    await db.flush()

    await downsampler._aggregate(db, "raw", "1m", 1, "2026-10-01T11:00:00")

    result = await db.execute(select(MetricPoint).where(MetricPoint.granularity == "1m").order_by(MetricPoint.ts))
    assert [(p.ts, p.cpu) for p in result.scalars()] == [
        ("2026-10-01T12:00:00", 20.0),
        ("2026-10-01T12:01:00", 50.0),
    ]


async def test_aggregate_raw_to_1m_does_not_merge_hour(db):
    # v1 缺陷回归锁：60 个分钟级 raw 点必须产出 60 个 1m 桶（曾被误并成 1 个小时桶）
    base = datetime(2026, 10, 1, 12, 0, 0, tzinfo=UTC)
    for i in range(60):
        db.add(MetricPoint(ts=_iso(base + timedelta(minutes=i)), granularity="raw", cpu=float(i)))
    await db.flush()

    await downsampler._aggregate(db, "raw", "1m", 1, "2026-10-01T00:00:00")

    result = await db.execute(select(MetricPoint.ts).where(MetricPoint.granularity == "1m"))
    assert len(result.all()) == 60


async def test_aggregate_temp_takes_max_and_disk_averages(db):
    db.add(MetricPoint(ts="2026-10-01T12:00:00", granularity="raw",
                       temp_max=40.0, disk_read_kbps=100.0, disk_write_kbps=20.0))
    db.add(MetricPoint(ts="2026-10-01T12:00:45", granularity="raw",
                       temp_max=55.5, disk_read_kbps=200.0, disk_write_kbps=40.0))
    await db.flush()

    await downsampler._aggregate(db, "raw", "1m", 1, "2026-10-01T00:00:00")

    point = (await db.execute(select(MetricPoint).where(MetricPoint.granularity == "1m"))).scalar_one()
    assert point.temp_max == 55.5
    assert point.disk_read_kbps == 150.0
    assert point.disk_write_kbps == 30.0


async def test_aggregate_1m_to_10m_boundaries(db):
    base = datetime(2026, 10, 1, 12, 0, 0, tzinfo=UTC)
    for i in range(30):  # 12:00..12:29 共 30 个分钟点
        db.add(MetricPoint(ts=_iso(base + timedelta(minutes=i)), granularity="1m", net_kbps=1.0))
    await db.flush()

    await downsampler._aggregate(db, "1m", "10m", 10, "2026-10-01T00:00:00")

    result = await db.execute(select(MetricPoint.ts).where(MetricPoint.granularity == "10m").order_by(MetricPoint.ts))
    assert [r[0] for r in result.all()] == [
        "2026-10-01T12:00:00",
        "2026-10-01T12:10:00",
        "2026-10-01T12:20:00",
    ]


async def test_purge_legacy_aggregates_runs_once(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(downsampler, "session_factory", maker)

    async with maker() as db:
        db.add(MetricPoint(ts="2026-10-01T12:00:00", granularity="raw", cpu=1.0))
        db.add(MetricPoint(ts="2026-10-01T12:00:00", granularity="1m", cpu=9.9))  # v1 失真行
        await db.commit()

    await downsampler.purge_legacy_aggregates()

    async with maker() as db:
        assert (await db.execute(select(MetricPoint.granularity))).scalars().all() == ["raw"]
        db.add(MetricPoint(ts="2026-10-01T12:05:00", granularity="1m", cpu=5.0))
        await db.commit()

    await downsampler.purge_legacy_aggregates()  # 幂等：标记已落库，新聚合不再被清除

    async with maker() as db:
        assert sorted((await db.execute(select(MetricPoint.granularity))).scalars().all()) == ["1m", "raw"]

    await engine.dispose()
