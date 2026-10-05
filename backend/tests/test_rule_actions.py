"""IF-THEN 剧本动作回归：actions 入队、fan_full/report 执行、失败落事件、非法值拒绝。"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.alert import AlertEvent, AlertRule
from app.services.alert import engine as alert_engine
from app.services.alert.engine import evaluate_tick, schedule_drain


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
def _reset_engine_state():
    alert_engine._tick_counters.clear()
    alert_engine._firing.clear()
    alert_engine._pending.clear()
    alert_engine._pending_actions.clear()
    yield
    alert_engine._tick_counters.clear()
    alert_engine._firing.clear()
    alert_engine._pending.clear()
    alert_engine._pending_actions.clear()


async def _make_rule(db, actions: list[str], **kw) -> AlertRule:
    rule = AlertRule(name="CPU 过载剧本", metric=kw.get("metric", "cpu_percent"),
                     comparator=">", threshold=kw.get("threshold", 90), duration_ticks=1,
                     severity="warning", channels=kw.get("channels", []), actions=actions, enabled=True)
    db.add(rule)
    await db.flush()
    return rule


def _ctx(cpu: float) -> dict:
    return {"cpu_percent": cpu, "mem_percent": 40.0, "temp_max": 45.0}


async def _drain_now():
    schedule_drain()
    if alert_engine._drain_task is not None:
        await alert_engine._drain_task


async def test_fire_queues_and_executes_actions(db, monkeypatch):
    calls = []

    def _fake_full(minutes=15):
        calls.append(("fan_full", minutes))
        return 1.0

    monkeypatch.setattr("app.services.control.fan_manager.request_full_speed", _fake_full)
    monkeypatch.setattr("app.services.report.diagnostic.generate_diagnostic", _AsyncRec(calls))
    await _make_rule(db, ["fan_full", "report"])

    fired = await evaluate_tick(db, _ctx(95))
    await db.commit()
    assert len(fired) == 1
    assert sorted(a for a, _r, _e in alert_engine._pending_actions) == ["fan_full", "report"]

    await _drain_now()
    assert ("fan_full", 15) in calls
    assert any(c[0] == "report" for c in calls)
    # 动作成功不产生额外事件
    events = (await db.execute(select(AlertEvent))).scalars().all()
    assert [e.metric for e in events] == ["cpu_percent"]


class _AsyncRec:
    def __init__(self, calls):
        self.calls = calls

    async def __call__(self, *a, **kw):
        self.calls.append(("report",) + a)


async def test_action_failure_records_event_and_continues(db, monkeypatch):
    calls = []

    def _boom(minutes=15):
        raise RuntimeError("pwm bus error")

    async def _diag_ok(redact):
        calls.append("report")

    monkeypatch.setattr("app.services.control.fan_manager.request_full_speed", _boom)
    monkeypatch.setattr("app.services.report.diagnostic.generate_diagnostic", _diag_ok)
    # 失败事件经引擎自建会话落库——指向本测试的内存库（默认工厂指向尚未建表的文件库）
    monkeypatch.setattr("app.db.session.session_factory", lambda: _session_ctx(db))
    await _make_rule(db, ["fan_full", "report"])

    assert await evaluate_tick(db, _ctx(95))
    await db.commit()
    assert len(alert_engine._pending_actions) == 2
    await _drain_now()

    assert calls == ["report"]  # fan_full 失败不中断 report
    events = (await db.execute(select(AlertEvent).where(AlertEvent.metric == "action:fan_full"))).scalars().all()
    assert len(events) == 1
    e = events[0]
    assert e.status == "resolved" and e.severity == "warning" and e.rule_id is None
    assert "pwm bus error" in e.message


def _session_ctx(session):
    class _C:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *exc):
            return False

    return _C()


async def test_invalid_action_not_queued(db):
    await _make_rule(db, ["fan_full", "bogus_action"])
    fired = await evaluate_tick(db, _ctx(95))
    await db.commit()
    assert len(fired) == 1
    assert alert_engine._pending_actions == [("fan_full", "CPU 过载剧本", fired[0]["id"])]


async def test_no_duplicate_actions_on_sustained_fire(db):
    await _make_rule(db, ["fan_full"], duration_ticks=1)
    assert await evaluate_tick(db, _ctx(95))
    assert await evaluate_tick(db, _ctx(95)) == []  # 仍 firing 不重复触发
    assert len(alert_engine._pending_actions) == 1


# ---- API：actions 字段与 metric pattern（含 M1 慢速规则补口） ----


async def test_rule_api_roundtrip_with_actions(client):
    data = (await client.post("/api/v1/alert/rules", json={
        "name": "剧本规则", "metric": "cpu_percent", "comparator": ">", "threshold": 90,
        "duration_ticks": 6, "severity": "warning", "channel_ids": [],
        "actions": ["fan_full", "report"], "enabled": True,
    }))
    assert data.status_code == 200, data.text
    rule_id = data.json()["data"]["id"]

    rules = (await client.get("/api/v1/alert/rules")).json()["data"]
    row = next(r for r in rules if r["id"] == rule_id)
    assert row["actions"] == ["fan_full", "report"]

    # 更新为单动作
    upd = await client.put(f"/api/v1/alert/rules/{rule_id}", json={
        "name": "剧本规则", "metric": "cpu_percent", "comparator": ">", "threshold": 90,
        "duration_ticks": 6, "severity": "warning", "channel_ids": [],
        "actions": ["report"], "enabled": True,
    })
    assert upd.status_code == 200
    rules = (await client.get("/api/v1/alert/rules")).json()["data"]
    assert next(r for r in rules if r["id"] == rule_id)["actions"] == ["report"]

    await client.delete(f"/api/v1/alert/rules/{rule_id}")


async def test_rule_api_rejects_bad_action_and_metric(client):

    r1 = await client.post("/api/v1/alert/rules", json={
        "name": "x", "metric": "cpu_percent", "comparator": ">", "threshold": 1,
        "actions": ["rm_rf"],
    })
    assert r1.status_code == 422  # actions pattern

    r2 = await client.post("/api/v1/alert/rules", json={
        "name": "y", "metric": "smart_rate:reallocated", "comparator": ">=", "threshold": 1,
    })
    assert r2.status_code == 200, r2.text  # M1 补口：慢速规则 metric 可建

    r3 = await client.post("/api/v1/alert/rules", json={
        "name": "z", "metric": "capacity_forecast", "comparator": "<=", "threshold": 30,
    })
    assert r3.status_code == 200, r3.text
