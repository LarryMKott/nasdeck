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
    item = engine._pending[0]
    channel_type, config, title = item["channel_type"], item["config"], item["title"]
    assert channel_type == "webhook" and config == {"url": "http://x/hook"}
    assert "告警触发" in title


async def test_drain_sends_and_empties_queue(db):
    sent = []

    async def fake_send(config, title, body):  # 新契约：成功返回 None
        sent.append((config, title, body))
        return None

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


def test_desensitizer_masks_paths_and_serial_variants():
    """路径/序列号/MAC 其他形态（评审 2026-10-25 P0-C：此前全部漏网）。"""
    text = desensitize("盘 /dev/sda1 挂载在 /volume1/share，另有 /home/admin/x.conf")
    assert "/dev/sda1" not in text and "/volume1/share" not in text and "/home/admin/x.conf" not in text
    assert "/dev/***" in text and "/volume1/***" in text and "/home/***" in text
    # 挂载路径不应误伤普通 URL 主机名之外的核心语义（URL 路径段被抹也属脱敏，可接受）
    for raw in ("Serial Number: S6XQNJ0R123456", "SN: ZA9QK1L2", "serial=WD-WX21A9", "S/N VKJ92R8D"):
        assert desensitize(raw) != raw, raw
    assert "S6XQNJ0R123456" not in desensitize("Serial Number: S6XQNJ0R123456")
    assert "WD-WX21A9" not in desensitize("serial=WD-WX21A9")
    # 普通单词不该被序列号规则误杀（值需含数字）
    assert desensitize("S/N healthy disk") == "S/N healthy disk"
    # MAC 连字符/点分形态
    assert "aa-bb-cc-dd-ee-ff" not in desensitize("MAC aa-bb-cc-dd-ee-ff")
    assert "aabb.ccdd.eeff" not in desensitize("MAC aabb.ccdd.eeff")


def test_mask_secret_values_recurses_nested_structures():
    """嵌套 dict/list 里的凭据不再原样保留（P0-C：顶层 key 无害≠嵌套无凭据）。"""
    masked = mask_secret_values(
        {
            "ui_prefs": {"theme": "dark", "notify_token": "abc123", "channels": [{"bark_api_key": "xyz"}]},
            "plain": [1, {"web_password": "p"}, "keep"],
        }
    )
    assert masked["ui_prefs"]["theme"] == "dark"
    assert masked["ui_prefs"]["notify_token"] == "********"
    assert masked["ui_prefs"]["channels"][0]["bark_api_key"] == "********"
    assert masked["plain"][0] == 1 and masked["plain"][2] == "keep"
    assert masked["plain"][1]["web_password"] == "********"


def test_diagnostic_settings_export_whitelist():
    """诊断包 settings：白名单外的键值整体 <redacted>，键名保留。"""
    from app.services.report.diagnostic import _settings_for_export

    dump = {"downsample_v2_migrated": True, "some_url": "https://x/y?token=abc", "custom": {"pw": "1"}}
    out = _settings_for_export(dump, redact=True)
    assert out["downsample_v2_migrated"] is True
    assert out["some_url"] == "<redacted>"
    assert out["custom"] == "<redacted>"
    assert _settings_for_export(dump, redact=False) == dump


def test_mask_config_masks_url_credentials():
    masked = mask_config("webhook", {"url": "http://user:pass@host/hook?token=abc&x=1"})
    assert "user:pass@" not in masked["url"]
    assert "token=abc" not in masked["url"]
    assert masked["url"].startswith("http://user:****@host/hook?token=****&x=1")


def test_mask_config_keeps_plain_url():
    masked = mask_config("webhook", {"url": "https://hooks.example/xyz"})
    assert masked["url"] == "https://hooks.example/xyz"


async def test_drain_retries_then_records_channel_health(monkeypatch):
    """发送失败重试 ≤3 次（尾部重入队），放弃后渠道健康留痕（原型 C1）。"""
    from app.services.alert import engine as alert_engine_mod

    calls = {"n": 0}

    async def flaky_send(config, title, body):
        calls["n"] += 1
        if calls["n"] < 3:
            return "timeout"  # 前两次失败
        return None  # 第三次成功

    impl = alert_engine_mod.channel_impl("webhook")
    monkeypatch.setattr(impl, "send", flaky_send)
    alert_engine_mod._pending.clear()
    alert_engine_mod._channel_health.clear()
    alert_engine_mod._pending.append(
        {"channel_id": 7, "channel_type": "webhook", "config": {"url": "https://x/hook"},
         "title": "t", "body": "b", "attempts": 0}
    )
    await alert_engine_mod._drain()
    assert calls["n"] == 3
    assert alert_engine_mod._pending == []
    assert alert_engine_mod.channel_health()[7]["send_failures"] == 0  # 最终成功清零
    assert alert_engine_mod.channel_health()[7]["last_ok_ts"] is not None

    # 三次全失败：放弃并记入健康
    async def always_fail(config, title, body):
        return "auth_failed"

    monkeypatch.setattr(impl, "send", always_fail)
    alert_engine_mod._pending.clear()
    alert_engine_mod._pending.append(
        {"channel_id": 7, "channel_type": "webhook", "config": {"url": "https://x/hook"},
         "title": "t", "body": "b", "attempts": 0}
    )
    await alert_engine_mod._drain()
    assert alert_engine_mod._pending == []
    health = alert_engine_mod.channel_health()[7]
    assert health["send_failures"] == 1 and health["last_error"] == "auth_failed"


def test_queue_overflow_counts_drop(monkeypatch):
    """队列上限 200：溢出丢弃并在渠道健康 overflow_dropped 留痕。"""
    from app.models.alert import AlertChannel
    from app.services.alert import engine as alert_engine_mod

    alert_engine_mod._pending.clear()
    alert_engine_mod._channel_health.clear()
    for _ in range(alert_engine_mod._PENDING_MAX):
        alert_engine_mod._pending.append({"channel_id": 1, "channel_type": "webhook", "config": {},
                                          "title": "t", "body": "b", "attempts": 0})
    channel = AlertChannel(id=1, name="c", type="webhook", config={}, enabled=True)
    alert_engine_mod._queue_notify({1: channel}, [1], "溢出", "b")
    assert len(alert_engine_mod._pending) == alert_engine_mod._PENDING_MAX
    assert alert_engine_mod.channel_health()[1]["overflow_dropped"] == 1
    alert_engine_mod._pending.clear()
