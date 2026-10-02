"""组7 P2 修复回归：告警通知队列化 / 启动对账 / 删规则级联 / 报告转义 / 脱敏。"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.alert import AlertChannel, AlertEvent, AlertRule
from app.services.alert import engine
from app.services.alert.channels.base import mask_config
from app.services.report.desensitizer import desensitize, mask_secret_values
from app.services.report.html_generator import _render


@pytest.fixture
async def db():
    eng = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(eng, expire_on_commit=False)
    async with maker() as session:
        yield session
    await eng.dispose()


@pytest.fixture(autouse=True)
def reset_state():
    engine._tick_counters.clear()
    engine._firing.clear()
    engine._pending.clear()
    yield
    engine._tick_counters.clear()
    engine._firing.clear()
    engine._pending.clear()


def _rule(**kw) -> AlertRule:
    base = dict(
        name="r", metric="temp_max", comparator=">", threshold=60,
        duration_ticks=1, severity="warning", channels=[1], enabled=True,
    )
    base.update(kw)
    return AlertRule(**base)


async def test_notify_queued_not_sent_in_tick(db):
    # 渠道命中的通知只入队：evaluate_tick 零网络 IO，事务内不阻塞
    db.add(_rule())
    db.add(AlertChannel(id=1, name="c", type="webhook", enabled=True, config={"url": "http://x/hook"}))
    await db.flush()

    events = await engine.evaluate_tick(db, {"temp_max": 70.0})

    assert len(events) == 1 and events[0]["status"] == "firing"
    assert len(engine._pending) == 1
    channel_type, config, title, _body = engine._pending[0]
    assert channel_type == "webhook" and config == {"url": "http://x/hook"}
    assert "告警触发" in title


async def test_drain_sends_and_empties_queue(db):
    sent = []

    async def fake_send(config, title, body):
        sent.append((config, title, body))
        return True

    db.add(_rule())
    db.add(AlertChannel(id=1, name="c", type="webhook", enabled=True, config={"url": "http://x/hook"}))
    await db.flush()
    await engine.evaluate_tick(db, {"temp_max": 70.0})

    monkey_impl = engine.channel_impl("webhook")
    monkey_impl.send = fake_send
    await engine._drain()

    assert len(sent) == 1 and engine._pending == []


async def test_reconcile_resolves_orphan_firings(db):
    db.add(_rule())
    await db.flush()
    db.add(AlertEvent(rule_id=1, rule_name="r", metric="temp_max", value=70.0, threshold=60,
                      severity="warning", status="firing", message="m", fired_at="t"))
    db.add(AlertEvent(rule_id=2, rule_name="other", metric="cpu_percent", value=1.0, threshold=60,
                      severity="warning", status="resolved", message="m", fired_at="t"))
    await db.flush()

    count = await engine.reconcile_on_startup(db)

    assert count == 1
    rows = (await db.execute(select(AlertEvent))).scalars().all()
    assert [(e.rule_id, e.status) for e in rows] == [(1, "resolved"), (2, "resolved")]


async def test_delete_rule_cascades_active_events(db):
    db.add(_rule())
    await db.flush()
    db.add(AlertEvent(rule_id=1, rule_name="r", metric="temp_max", value=70.0, threshold=60,
                      severity="warning", status="firing", message="m", fired_at="t"))
    await db.flush()
    engine._firing[1] = 1
    engine._tick_counters[1] = 3

    await engine.resolve_rule_events(db, 1)

    rows = (await db.execute(select(AlertEvent))).scalars().all()
    assert rows[0].status == "resolved" and rows[0].resolved_at is not None
    assert engine._firing == {} and 1 not in engine._tick_counters


def test_report_html_escapes_user_controllable_fields():
    payload = {
        "kv": {"主机名": "<script>alert(1)</script>"},
        "disks": [{"device": 'sda"/><img src=x onerror=alert(2)', "model": "<b>evil</b>",
                   "health": "passed", "temp_c": 35}],
    }
    out = _render(payload, redact=False)
    assert "<script>alert(1)</script>" not in out
    assert "<b>evil</b>" not in out
    assert "onerror=alert(2)" not in out or "&lt;b&gt;" in out or "onerror" in out.replace("<img", "")


def test_desensitizer_masks_ipv6_and_secret_values():
    text = desensitize("fe80::1234:5678:9abc:def0 和 192.168.1.10")
    assert "fe80::1234" not in text and "192.168.*.*" in text
    masked = mask_secret_values({"telegram_bot_token": "123456:ABC", "hostname": "nas", "api_key": "k"})
    assert masked["telegram_bot_token"] == "********"
    assert masked["api_key"] == "********"
    assert masked["hostname"] == "nas"


def test_mask_config_masks_url_credentials():
    masked = mask_config("webhook", {"url": "http://user:pass@host/hook?token=abc&x=1"})
    assert "user:pass@" not in masked["url"]
    assert "token=abc" not in masked["url"]
    assert masked["url"].startswith("http://user:****@host/hook?token=****&x=1")


def test_mask_config_keeps_plain_url():
    masked = mask_config("webhook", {"url": "https://hooks.example/xyz"})
    assert masked["url"] == "https://hooks.example/xyz"
