"""只读跑分回归：状态机互斥、standby 不唤醒、参数钳制、惰性落库（花活二期 Q）。"""

from __future__ import annotations

import platform

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.exceptions import ExternalToolError, StateConflictError
from app.db.base import Base
from app.services.storage import benchmark
from tests.conftest import ok


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.fixture(autouse=True)
def _reset_state():
    benchmark.reset_for_test()
    yield
    benchmark.reset_for_test()


@pytest.fixture
def _linux_ready(monkeypatch):
    """注入 Linux 平台 + 盘在清单 + 非 standby + 线程桩（worker 主体不在单测里跑）。"""
    monkeypatch.setattr(benchmark.platform, "system", lambda: "Linux")

    async def _fake_disks():
        return [{"device": "sda"}, {"device": "sdb"}]

    async def _fake_report(device):
        return {"device": device, "standby": False}

    monkeypatch.setattr(benchmark.volume_service, "list_disks", _fake_disks)
    monkeypatch.setattr(benchmark.smart_service, "smart_report", _fake_report)
    monkeypatch.setattr(benchmark.threading, "Thread", lambda **kw: type("T", (), {"start": lambda self: None})())


async def test_start_running_state_and_conflict(_linux_ready):
    snap = await benchmark.start("sda", 20, 30)
    assert snap["status"] == "running" and snap["device"] == "sda"
    assert snap["started_at"] is not None
    with pytest.raises(StateConflictError):  # 全局同一时间只允许一个（1005）
        await benchmark.start("sdb", 20, 30)


async def test_start_rejects_standby_without_waking(monkeypatch, _linux_ready):
    """standby 盘默认跳过：拒触发且不打扰休眠（-n standby 探测路径）。"""

    async def _standby_report(device):
        return {"device": device, "standby": True}

    monkeypatch.setattr(benchmark.smart_service, "smart_report", _standby_report)
    with pytest.raises(StateConflictError, match="休眠"):
        await benchmark.start("sda")


async def test_start_rejects_non_linux(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    with pytest.raises(ExternalToolError):
        await benchmark.start("sda")


async def test_unknown_device_rejected(_linux_ready):
    from app.core.exceptions import NotFoundError

    with pytest.raises(NotFoundError):
        await benchmark.start("sdzz")


async def test_cancel_sets_flag(_linux_ready):
    await benchmark.start("sda")
    snap = benchmark.cancel()
    assert benchmark._state["stop"] is True and snap["status"] == "running"  # 协作式：不瞬断
    assert benchmark.cancel()["status"] == "running"


async def test_lazy_persist_and_history(db):
    """done 成绩首次被观测时落库：history() 触发 maybe_persist。"""
    benchmark._state.update(
        status="done",
        device="sda",
        seconds=20,
        duty=30,
        direct=True,
        elapsed=20.0,
        bytes_read=20 * 8 * 1048576,  # 墙钟均值 8 MB/s
        curve=[{"t": 0.5, "mbps": 8.0}, {"t": 1.0, "mbps": 9.2}],
    )
    rows = await benchmark.history(db)
    assert len(rows) == 1
    assert rows[0]["device"] == "sda" and rows[0]["avg_mbps"] == 8.0
    assert rows[0]["peak_mbps"] == 9.2 and rows[0]["direct"] is True
    assert len(rows[0]["curve"]) == 2
    assert benchmark._state["result_id"] == rows[0]["id"]  # 幂等标记
    again = await benchmark.history(db)
    assert len(again) == 1  # 不重复落库


async def test_history_device_filter(db):
    benchmark._state.update(status="done", device="sda", elapsed=1.0, bytes_read=1048576)
    await benchmark.history(db)
    benchmark._state.update(status="done", device="sdb", elapsed=1.0, bytes_read=1048576, result_id=None)
    await benchmark.history(db)
    rows = await benchmark.history(db, device="sdb")
    assert len(rows) == 1 and rows[0]["device"] == "sdb"


# ---- API：response_model 过滤回归锁 ----


async def test_bench_api_shape(client, _linux_ready):
    state = ok(await client.get("/api/v1/storage/benchmarks/current"))
    assert state["status"] == "idle" and "curve" in state and "progress" in state
    assert ok(await client.get("/api/v1/storage/benchmarks")) == []
