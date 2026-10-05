"""RAID 同步进度解析与活动转换监视回归（M2.4）。"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.alert import AlertEvent
from app.services.alert import engine as alert_engine
from app.services.storage import raid as raid_service
from app.services.storage import sync_watch

_MD_SYNCING = """md0 : active raid6 sda2[0] sdb2[1] sdc2[2] sdd2[3]
      8790400320 blocks super 1.2 level 6, 512k chunk, algorithm 18 [4/4] [UUUU]
      [===========>.........]  resync = 52.3% (1823948288/2930133440) finish=123.4min speed=148736K/sec
      bitmap: 0/22 pages [0KB], 65536KB chunk

unused devices: <none>
"""

_MD_IDLE = """md0 : active raid6 sda2[0] sdb2[1] sdc2[2] sdd2[3]
      8790400320 blocks super 1.2 level 6, 512k chunk, algorithm 18 [4/4] [UUUU]
      bitmap: 0/22 pages [0KB], 65536KB chunk

unused devices: <none>
"""

_MD_DELAYED = """md1 : active raid1 sde1[0] sdf1[1]
      976631192 blocks super 1.2 [2/2] [UU]
      [>....................]  check = 1.2% (123456/976631192) finish=98.7min speed=16400K/sec

unused devices: <none>
"""


def test_mdstat_sync_progress_parsed(monkeypatch):
    monkeypatch.setattr(raid_service, "read_text", lambda path: _MD_SYNCING)
    vols = raid_service._mdstat_volumes()
    assert len(vols) == 1
    sync = vols[0]["details"]["sync"]
    assert sync["action"] == "resync"
    assert sync["percent"] == pytest.approx(52.3)
    assert sync["finish_text"] == "123.4min"
    assert sync["speed_text"] == "148736K/s"
    assert vols[0]["healthy"] is True  # 同步不等于降级


def test_mdstat_no_sync_section(monkeypatch):
    monkeypatch.setattr(raid_service, "read_text", lambda path: _MD_IDLE)
    vols = raid_service._mdstat_volumes()
    assert "sync" not in vols[0]["details"]


def test_mdstat_sync_percent_optional(monkeypatch):
    # delayed 形态无百分比：进度条显示"等待调度"
    text = _MD_DELAYED.replace("check = 1.2% (123456/976631192) finish=98.7min speed=16400K/sec", "check = delayed")
    monkeypatch.setattr(raid_service, "read_text", lambda path: text)
    vols = raid_service._mdstat_volumes()
    sync = vols[0]["details"]["sync"]
    assert sync["action"] == "check" and sync["percent"] is None


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
def _reset():
    sync_watch.reset_for_test()
    alert_engine._pending.clear()
    yield
    sync_watch.reset_for_test()
    alert_engine._pending.clear()


def _raid_response(sync: dict | None) -> dict:
    vol = {
        "source": "mdadm", "controller": "soft", "volume_id": "md0", "name": "md0",
        "level": "6", "state": "clean", "healthy": True,
        "details": {"sync": sync} if sync else {},
    }
    return {"software_raid": [vol], "hardware_raid": []}


async def test_sync_transitions_started_and_finished(monkeypatch):
    seq = [
        _raid_response(None),
        _raid_response({"action": "recovery", "percent": 10.0}),
        _raid_response({"action": "recovery", "percent": 80.0}),  # 进行中不重复报
        _raid_response(None),
    ]
    monkeypatch.setattr(sync_watch.raid_service, "raid_status", _AsyncR(seq))

    assert await sync_watch.detect_sync_transitions() == []
    started = await sync_watch.detect_sync_transitions()
    assert len(started) == 1 and started[0]["phase"] == "started" and started[0]["action"] == "recovery"
    assert await sync_watch.detect_sync_transitions() == []
    finished = await sync_watch.detect_sync_transitions()
    assert len(finished) == 1 and finished[0]["phase"] == "finished"


class _AsyncR:
    def __init__(self, seq):
        self.seq = seq

    async def __call__(self):
        return self.seq.pop(0)


async def test_persist_started_event_and_broadcast(db, monkeypatch):
    alert_engine._pending.clear()
    from datetime import UTC, datetime

    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    db.add(
        AlertEvent(
            rule_id=None, rule_name="阵列同步", metric="raid_sync", value=None, threshold=None,
            severity="warning", status="resolved", message="阵列 md0 开始recovery", fired_at=now, resolved_at=now,
        )
    )
    await db.commit()
    events = (await db.execute(select(AlertEvent).where(AlertEvent.metric == "raid_sync"))).scalars().all()
    assert len(events) == 1 and events[0].severity == "warning"
