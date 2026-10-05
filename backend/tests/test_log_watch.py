"""日志哨兵回归：正则命中、24h 去重、平台降级、落库广播。"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.alert import AlertEvent  # noqa: F401 先于 create_all 注册 metadata
from app.services.alert import engine as alert_engine
from app.services.system import log_watch


@pytest.fixture(autouse=True)
def _reset():
    log_watch.reset_for_test()
    alert_engine._pending.clear()
    yield
    log_watch.reset_for_test()
    alert_engine._pending.clear()


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


def _lines() -> list[str]:
    return [
        "Oct  5 21:00:01 nas kernel: blk_update_request: I/O error, dev sdb, sector 12345 op 0x1",
        "Oct  5 21:00:02 nas kernel: sd 1:0:0:0: [sdb] tag#12 FAILED Result: uncorrectable sector",
        "Oct  5 21:00:03 nas kernel: mce: [Hardware Error]: Machine check events logged",  # 不命中
        "Oct  5 21:00:04 nas kernel: Out of memory: Killed process 1234 (plex)",
        "Oct  5 21:00:05 nas kernel: sda: thermal throttling, temperature above threshold",
    ]


def test_match_lines_hits_expected():
    hits = log_watch.match_lines(_lines())
    assert len(hits) == 4  # I/O error / uncorrectable / OOM / thermal
    assert all("hash" in h and "line" in h for h in hits)


def test_dedup_same_line_24h():
    lines = _lines()
    assert len(log_watch.match_lines(lines)) == 4
    assert log_watch.match_lines(lines) == []  # 同行 24h 内不重复


def test_repeated_storm_dedup():
    line = "md/raid1: md0: not enough operational devices"
    assert len(log_watch.match_lines([line] * 50)) == 1


async def test_watch_tick_non_linux(monkeypatch):
    import app.services.system.log_watch as lw

    monkeypatch.setattr(lw.platform, "system", lambda: "Windows")
    assert await lw.watch_tick() == []


async def test_watch_tick_journalctl_missing(monkeypatch):
    import app.services.system.log_watch as lw

    async def _boom(*args, **kwargs):
        raise RuntimeError("journalctl missing")

    monkeypatch.setattr(lw, "run_cmd", _boom)
    monkeypatch.setattr(lw.platform, "system", lambda: "Linux")
    assert await lw.watch_tick() == []


async def test_persist_and_notify(db):
    from sqlalchemy import select

    alert_engine._pending.clear()
    hits = log_watch.match_lines(_lines())
    await log_watch.persist_and_notify(db, hits)
    await db.commit()
    events = (await db.execute(select(AlertEvent).where(AlertEvent.metric == "log_alert"))).scalars().all()
    assert len(events) == 4
    assert all(e.status == "resolved" and e.severity == "warning" for e in events)
    assert any("I/O error" in e.message for e in events)
