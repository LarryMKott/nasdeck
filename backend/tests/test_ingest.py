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


async def test_worker_self_heals_and_counts_restarts(monkeypatch):
    """worker 意外死亡：done_callback 记数并安排退避重建（评审 2026-10-25 N8/B1）。"""
    ingest._reset_for_test()
    real_run = ingest._run
    calls = {"n": 0}

    async def _flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("worker explode")
        await real_run()  # 重建后转正常运行，验证自愈闭环稳定

    monkeypatch.setattr(ingest, "_run", _flaky)
    # 退避改为 0，重建立即发生
    monkeypatch.setattr(ingest, "_RESTART_BACKOFF", (0,))
    ingest.start()
    await asyncio.sleep(0.3)  # 等 done_callback + call_later(0) 重建

    assert ingest.stats()["worker_restarts"] == 1
    assert ingest.stats()["worker_running"] is True
    assert "worker explode" in (ingest.stats()["last_error"] or "")
    await ingest.stop()


async def test_stats_reports_queue_and_drops(monkeypatch):
    monkeypatch.setattr(ingest, "_QUEUE_MAX", 2)
    ingest._reset_for_test()
    ingest.start()
    for i in range(6):
        ingest.submit("metrics", {"ts": f"2030-02-01T01:00:{i:02d}", "granularity": "raw", "cpu": 1.0})
    snap = ingest.stats()
    assert snap["queue_depth"] == 2 and snap["queue_capacity"] == 2
    assert snap["dropped_total"] == 4
    assert snap["worker_running"] is True
    await ingest.stop()
