"""ingest 单写者落库通道：攒批、冲突跳过、队列满丢弃。"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select

from app.db import ingest
from app.models.metrics import MetricPoint


async def _drain_until(min_rows: int, timeout: float = 8.0) -> int:
    """等待本测试前缀的行落盘 ≥min_rows（ingest 批量写不实时可见；全表有其他测试数据）。"""
    from app.db.session import session_factory

    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        async with session_factory() as db:
            n = len(
                (await db.execute(select(MetricPoint.ts).where(MetricPoint.ts.like("2030%")))).all()
            )
        if n >= min_rows:
            return n
        await asyncio.sleep(0.1)
    raise AssertionError(f"超时：预期落库 ≥{min_rows} 行")


@pytest.fixture(autouse=True)
async def _worker(monkeypatch):
    monkeypatch.setattr(ingest, "_FLUSH_INTERVAL", 0.3)  # 加快攒批节奏
    ingest._reset_for_test()
    ingest.start()
    yield
    await ingest.stop()
    ingest._reset_for_test()


async def test_batch_insert_and_conflict_skip(client):
    from app.db.session import session_factory

    for i in range(3):  # 三行不同主键
        ingest.submit("metrics", {"ts": f"2030-01-01T00:00:0{i}", "granularity": "raw", "cpu": i + 0.5})
    ingest.submit("metrics", {"ts": "2030-01-01T00:00:00", "granularity": "raw", "cpu": 9.9})  # 与首行同键
    n = await _drain_until(3)
    assert n == 3
    async with session_factory() as db:
        row = (
            await db.execute(
                select(MetricPoint).where(
                    MetricPoint.ts == "2030-01-01T00:00:00", MetricPoint.granularity == "raw"
                )
            )
        ).scalar_one()
    assert row.cpu == 0.5  # 首行生效、冲突行跳过、批不失败


async def test_hardware_rows_via_same_channel(client):
    from sqlalchemy import func

    from app.db.session import session_factory
    from app.models.hardware import HardwareItem

    ingest.submit("hardware", {"kind": "cpu", "name": "Test CPU", "props": {"available": True}})
    ingest.submit("hardware", {"kind": "gpu", "name": "", "props": {"available": False}})
    n = 0
    deadline = asyncio.get_event_loop().time() + 8
    while asyncio.get_event_loop().time() < deadline:
        async with session_factory() as db:
            n = (await db.execute(select(func.count(HardwareItem.id)))).scalar()
        if n >= 2:
            break
        await asyncio.sleep(0.1)
    assert n >= 2


async def test_queue_full_drops_not_blocks(monkeypatch):
    monkeypatch.setattr(ingest, "_QUEUE_MAX", 2)
    ingest._reset_for_test()
    ingest.start()
    for i in range(10):  # 超 2 条容量：多余的丢，submit 不抛不阻塞
        ingest.submit("metrics", {"ts": f"2030-02-01T00:00:{i:02d}", "granularity": "raw", "cpu": 1.0})
    assert ingest._queue.qsize() == 2
