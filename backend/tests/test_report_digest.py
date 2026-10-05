"""周报生成与调度回归：摘要口径、窗口判定、手动广播、API 往返。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.alert import AlertEvent
from app.models.metrics import MetricPoint
from app.models.system import SystemSetting  # noqa: F401 先于 create_all 注册 metadata
from app.services.alert import engine as alert_engine
from app.services.report import digest
from tests.conftest import ok


def _now(weekday: int, hour: int) -> datetime:
    """2026-01-05 是周一。"""
    return datetime(2026, 1, 5 + weekday, hour, 7, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _reset_pending():
    alert_engine._pending.clear()
    yield
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


async def _seed_activity(db):
    from app.models.alert import AlertChannel

    db.add(AlertChannel(name="TG", type="telegram", config={"bot_token": "t", "chat_id": "1"}))
    db.add(AlertEvent(rule_id=None, rule_name="温度规则", metric="temp_max", value=61.0,
                      threshold=60, severity="warning", status="resolved",
                      message="温度超阈值", fired_at="2026-01-03T10:00:00+00:00",
                      resolved_at="2026-01-03T10:05:00+00:00"))
    db.add(MetricPoint(ts="2026-01-03T10:00:00", granularity="1m", temp_max=63.5))
    await db.commit()


async def test_digest_composition(db):
    await _seed_activity(db)
    text = await digest.build_digest(db, now=datetime(2026, 1, 5, 9, 0, tzinfo=UTC))
    assert "NAS 周报" in text
    assert "近 7 天告警事件 1 次" in text
    assert "63.5 °C" in text
    assert "SMART" in text  # smart_history 空表 → 无增长分支


def test_due_window_and_dedup():
    cfg = {"enabled": True, "weekday": 0, "hour": 9}
    assert digest.due(cfg, _now(0, 9), last_run="2026-01-01")
    assert not digest.due(cfg, _now(0, 9), last_run="2026-01-05")  # 当天已跑
    assert not digest.due(cfg, _now(0, 10), last_run="")
    assert not digest.due(cfg, _now(1, 9), last_run="")
    assert not digest.due({"enabled": False, "weekday": 0, "hour": 9}, _now(0, 9), "")


async def test_schedule_tick_fires_once(db):
    from app.models.alert import AlertChannel

    db.add(AlertChannel(name="TG", type="telegram", config={"bot_token": "t", "chat_id": "1"}))
    await digest.save_schedule(db, {"enabled": True, "weekday": 0, "hour": 9})
    await db.commit()
    assert await digest.schedule_tick(db, now=_now(0, 9)) is True
    assert alert_engine._pending  # 摘要已入队（广播）
    assert await digest.schedule_tick(db, now=_now(0, 9)) is False  # 当天去重
    assert await digest.schedule_tick(db, now=_now(1, 9)) is False  # 星期外


async def test_push_now_queues_notification(db):
    await _seed_activity(db)
    text = await digest.push_now(db)
    assert "NAS 周报" in text
    assert any(title == "NAS 周报" for _ch, _config, title, _body in alert_engine._pending)


# ---- API ----


async def test_report_schedule_api_roundtrip(client):
    default = ok(await client.get("/api/v1/system/report-schedule"))
    assert default["enabled"] is False

    saved = ok(await client.put("/api/v1/system/report-schedule",
                                json={"enabled": True, "weekday": 5, "hour": 8}))
    assert saved == {"enabled": True, "weekday": 5, "hour": 8, "last_run": None}


async def test_send_report_now_api(client):
    data = ok(await client.post("/api/v1/system/report/send", json={}))
    assert "NAS 周报" in data["digest"]
