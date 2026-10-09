"""降采样「只聚合已封口桶」测试（A1）：当前桶不写、封口桶完整聚合且幂等、
部分桶不被 have 查重永久冻结（回归锁）。

时间源：_aggregate 的当前桶键与 downsample_tick 的 cutoff 都经模块级
_iso_minutes_ago() 取「现在」，整体 monkeypatch 为可控假钟，桶判定全确定。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.metrics import MetricPoint
from app.tasks import downsampler


class _Clock:
    """可控假钟：_fake_iso_minutes_ago 的「现在」，用例内可推进。"""

    now = datetime(2026, 10, 9, 12, 5, 50, tzinfo=UTC)


def _fake_iso_minutes_ago(minutes: int) -> str:
    return (_Clock.now - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S")


@pytest.fixture(autouse=True)
def fake_clock(monkeypatch):
    """替换模块时间源：当前桶判定与 raw 保留窗 cutoff 全部随 _Clock 走。"""
    monkeypatch.setattr(downsampler, "_iso_minutes_ago", _fake_iso_minutes_ago)
    _Clock.now = datetime(2026, 10, 9, 12, 5, 50, tzinfo=UTC)
    return _Clock


@pytest.fixture
async def maker(monkeypatch):
    """内存库 + session_factory 指向测试库（downsample_tick 自管会话）。

    须先导入 app.models.hardware 再建表：tick 内 _prune_hardware_items 会
    delete hardware_items，表缺失时整轮异常被吞、commit 不执行。
    """
    import app.models.hardware  # noqa: F401

    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker_ = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(downsampler, "session_factory", maker_)
    yield maker_
    await engine.dispose()


async def _seed_raw(maker, rows: list[tuple[str, float]]) -> None:
    async with maker() as db:
        for ts, cpu in rows:
            db.add(MetricPoint(ts=ts, granularity="raw", cpu=cpu))
        await db.commit()


async def _one_m_rows(maker) -> list[tuple[str, float | None]]:
    async with maker() as db:
        result = await db.execute(
            select(MetricPoint).where(MetricPoint.granularity == "1m").order_by(MetricPoint.ts)
        )
        return [(p.ts, p.cpu) for p in result.scalars()]


# ---------------- A1 用例 A：当前桶不写 ----------------


async def test_current_bucket_not_written(maker, fake_clock):
    """当前分钟仍是写入中的桶：即使已有部分 raw 数据也不产出 1m 桶。"""
    await _seed_raw(
        maker,
        [
            ("2026-10-09T12:04:00", 10.0),  # 已封口的前一分钟（同时充当执行哨兵）
            ("2026-10-09T12:04:30", 30.0),
            ("2026-10-09T12:05:10", 20.0),  # 当前分钟（假钟 12:05:50）
            ("2026-10-09T12:05:40", 40.0),
        ],
    )

    await downsampler.downsample_tick()

    # 前一分钟完整聚合（证明 tick 确实执行了），当前分钟桶不存在
    assert await _one_m_rows(maker) == [("2026-10-09T12:04:00", 20.0)]


# ---------------- A1 用例 B：已封口桶完整聚合 + 幂等 ----------------


async def test_sealed_bucket_aggregates_and_idempotent(maker, fake_clock):
    await _seed_raw(maker, [("2026-10-09T12:04:05", 10.0), ("2026-10-09T12:04:35", 30.0)])

    await downsampler.downsample_tick()
    assert await _one_m_rows(maker) == [("2026-10-09T12:04:00", 20.0)]

    # 幂等：have 查重命中，重复 tick 不新增也不改写
    await downsampler.downsample_tick()
    assert await _one_m_rows(maker) == [("2026-10-09T12:04:00", 20.0)]


# ---------------- A1 用例 C：部分桶不被 have 查重冻结（回归锁） ----------------


async def test_partial_bucket_not_frozen_by_have_dedup(maker, fake_clock):
    """同一分钟先半量（无桶）→ 钟推进封口后补全量（桶=全量均值）。

    v1 缺陷：首轮以部分均值入桶后，下一轮该桶键进 have 集合被永久跳过，
    残缺均值冻结为最终数据——本用例锁死修复后的重聚行为。
    """
    fake_clock.now = datetime(2026, 10, 9, 12, 3, 50, tzinfo=UTC)
    await _seed_raw(maker, [("2026-10-09T12:03:10", 10.0)])

    await downsampler.downsample_tick()
    assert await _one_m_rows(maker) == []  # 当前桶未封口：部分数据不入桶

    fake_clock.now = datetime(2026, 10, 9, 12, 4, 10, tzinfo=UTC)  # 钟推进：12:03 桶已封口
    await _seed_raw(maker, [("2026-10-09T12:03:30", 30.0)])

    await downsampler.downsample_tick()
    assert await _one_m_rows(maker) == [("2026-10-09T12:03:00", 20.0)]  # 全量均值，而非残缺 10.0
