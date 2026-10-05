"""SMART 周期巡检回归：计划持久化/默认值、触发窗口判定、巡检结果落事件与广播。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.services.storage import selftest_schedule
from app.tasks.collectors import selftest_10m
from tests.conftest import ok


def _dt(weekday: int, hour: int) -> datetime:
    """2026-01-05 是周一。"""
    return datetime(2026, 1, 5 + weekday, hour, 7, 0, tzinfo=UTC)


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
def _reset_running():
    selftest_schedule._running = None
    yield
    selftest_schedule._running = None


async def test_load_defaults_and_validation(db):
    cfg = await selftest_schedule.load_schedule(db)
    assert cfg == {"enabled": False, "weekday": 6, "hour": 4, "type": "short"}
    await selftest_schedule.save_schedule(db, {"enabled": True, "weekday": 9, "hour": -3, "type": "bogus"})
    cfg = await selftest_schedule.load_schedule(db)
    assert cfg["weekday"] == 6 and cfg["hour"] == 0 and cfg["type"] == "short"  # 越界钳制
    assert cfg["enabled"] is True  # 合法键保留


def test_due_window():
    cfg = {"enabled": True, "weekday": 2, "hour": 5, "type": "short"}
    assert selftest_schedule._due(cfg, _dt(2, 5), last_run="2026-01-01")
    assert not selftest_schedule._due(cfg, _dt(2, 6), last_run="2026-01-01")  # 小时不符
    assert not selftest_schedule._due(cfg, _dt(3, 5), last_run="2026-01-01")  # 星期不符
    assert not selftest_schedule._due(cfg, _dt(2, 5), last_run="2026-01-07")  # 当天已跑


async def test_tick_triggers_once_per_window(db, monkeypatch):
    await selftest_schedule.save_schedule(db, {"enabled": True, "weekday": 0, "hour": 5, "type": "short"})
    monkeypatch.setattr(selftest_schedule, "run_scheduled_selftest", _Recorder())
    assert await selftest_schedule.schedule_tick(db, now=_dt(0, 5)) is True
    if selftest_schedule._running is not None:
        await selftest_schedule._running  # 后台 task 收尾，避免悬挂在事件循环上
    assert await selftest_schedule.schedule_tick(db, now=_dt(0, 5)) is False  # 当天已跑
    assert await selftest_schedule.schedule_tick(db, now=_dt(0, 6)) is False  # 窗口外
    assert await selftest_schedule.schedule_tick(db, now=_dt(1, 5)) is False  # 星期外
    # 下周同窗口再触发
    next_week = _dt(0, 5).replace(day=12)
    assert await selftest_schedule.schedule_tick(db, now=next_week) is True
    if selftest_schedule._running is not None:
        await selftest_schedule._running


class _Recorder:
    """可等待的巡检替身：schedule_tick 起的 task 引用真实 _run_with_own_session，
    其内部调用 run_scheduled_selftest —— monkeypatch 打在这一名字上。"""

    async def __call__(self, db):
        self.called_with = db


async def test_tick_disabled_never_fires(db):
    await selftest_schedule.save_schedule(db, {"enabled": False, "weekday": 0, "hour": 5, "type": "short"})
    assert await selftest_schedule.schedule_tick(db, now=_dt(0, 5)) is False


async def test_scheduled_run_records_events(db, monkeypatch):
    # 盘清单/自检替身：一块盘正常完成、一块盘发起失败
    async def _fake_disks():
        return [{"device": "sda"}, {"device": "sdb"}]

    monkeypatch.setattr(selftest_schedule.volume_service, "list_disks", _fake_disks)
    monkeypatch.setattr(selftest_schedule.smart_history, "smart_key", lambda d: d)

    class FakeEngine:
        def __init__(self):
            self.calls = []

        def start_test(self, dev, test_type, runner=None, probe=None):
            self.calls.append(dev)
            if dev == "sdb":
                raise RuntimeError("smartctl missing")
            from app.services.storage import self_test

            self_test._tests[dev] = {
                "device": dev, "type": test_type, "status": "done", "started_at": "",
                "completed_at": "", "percent": 100, "result": "completed", "error": None,
            }
            return dict(self_test._tests[dev])

        def get_test(self, dev):
            from app.services.storage import self_test

            return self_test._tests[dev]

    fake = FakeEngine()
    monkeypatch.setattr(selftest_schedule.self_test, "start_test", fake.start_test)
    monkeypatch.setattr(selftest_schedule.self_test, "get_test", fake.get_test)

    await selftest_schedule.run_scheduled_selftest(db)
    from sqlalchemy import select

    from app.models.alert import AlertEvent

    events = (await db.execute(select(AlertEvent))).scalars().all()
    assert [e.message.split(" ")[0] for e in events] == ["sda", "sdb"]
    assert all(e.status == "resolved" and e.rule_name == "SMART 周期巡检" for e in events)
    assert [e.severity for e in events] == ["info", "warning"]  # 失败盘 warning
    assert fake.calls == ["sda", "sdb"]  # 串行：sdb 发起失败不阻断 sda 先完成


async def test_scheduler_tick_job_registered():
    from app.tasks import scheduler as sched

    sched.start_jobs()
    try:
        ids = {j.id for j in sched.scheduler.get_jobs()}
        assert "selftest_10m" in ids
    finally:
        sched.scheduler.remove_all_jobs()
    # tick 本身异常吞掉不炸调度
    await selftest_10m.selftest_tick()


# ---- API：GET/PUT /system/selftest-schedule ----


async def test_schedule_api_roundtrip(client):
    default = ok(await client.get("/api/v1/system/selftest-schedule"))
    assert default["enabled"] is False and default["last_run"] is None

    saved = ok(
        await client.put(
            "/api/v1/system/selftest-schedule",
            json={"enabled": True, "weekday": 5, "hour": 3, "type": "long"},
        )
    )
    assert saved == {"enabled": True, "weekday": 5, "hour": 3, "type": "long", "last_run": None}

    again = ok(await client.get("/api/v1/system/selftest-schedule"))
    assert again["enabled"] is True and again["type"] == "long"


async def test_schedule_api_rejects_invalid(client):
    from tests.conftest import err

    # Pydantic 校验失败走 RequestValidationError 处理器 → 信封 2000
    body = err(
        await client.put(
            "/api/v1/system/selftest-schedule",
            json={"enabled": True, "weekday": 9, "hour": 3, "type": "short"},
        ),
        2000,
    )
    assert "weekday" in str(body["message"])
