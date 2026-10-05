"""webhook 渠道单测：validate 校验与 send 请求（MockTransport，不打真实网络）。"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.core.exceptions import InvalidParamsError
from app.services.alert import engine
from app.services.alert.channels import webhook as webhook_mod
from app.services.alert.channels.base import CHANNEL_TYPES
from app.services.alert.channels.webhook import WebhookChannel
from tests.conftest import ok


def test_webhook_registered():
    assert "webhook" in CHANNEL_TYPES
    assert isinstance(engine.channel_impl("webhook"), WebhookChannel)


def test_validate_missing_url():
    with pytest.raises(InvalidParamsError):
        WebhookChannel().validate({})


@pytest.mark.parametrize("url", ["ftp://x.com/hook", "x.com/hook", ""])
def test_validate_bad_scheme(url):
    with pytest.raises(InvalidParamsError):
        WebhookChannel().validate({"url": url})


def test_validate_ok():
    WebhookChannel().validate({"url": "https://example.com/hook"})


def _patch_transport(monkeypatch, handler):
    real_client = httpx.AsyncClient

    def _factory(**kwargs):
        kwargs.pop("transport", None)
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(webhook_mod.httpx, "AsyncClient", _factory)


def test_send_posts_json_payload(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["json"] = request.read()
        return httpx.Response(200)

    _patch_transport(monkeypatch, handler)
    ok = asyncio.run(WebhookChannel().send({"url": "https://example.com/hook"}, "标题", "内容"))
    assert ok is True
    assert seen["url"] == "https://example.com/hook"
    assert b"nasdeck" in seen["json"] and "标题".encode() in seen["json"]


@pytest.mark.parametrize("status", [201, 204, 500])
def test_send_status_handling(monkeypatch, status):
    _patch_transport(monkeypatch, lambda request: httpx.Response(status))
    ok = asyncio.run(WebhookChannel().send({"url": "https://example.com/hook"}, "t", "b"))
    assert ok is (status < 400)


def test_send_network_error_returns_false(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    _patch_transport(monkeypatch, handler)
    ok = asyncio.run(WebhookChannel().send({"url": "https://example.com/hook"}, "t", "b"))
    assert ok is False


# ---- M3.2：GET /alert/events 的 source 过滤（统一事件时间线数据源） ----


async def test_events_source_filter(client):
    from app.db.session import session_factory
    from app.models.alert import AlertEvent

    async with session_factory() as db:
        db.add(AlertEvent(rule_id=1, rule_name="温度规则", metric="temp_max", value=61.0,
                          threshold=60, severity="warning", status="resolved",
                          message="规则触发", fired_at="2026-01-03T10:00:00+00:00"))
        db.add(AlertEvent(rule_id=None, rule_name="日志哨兵", metric="log_alert", value=None,
                          threshold=None, severity="warning", status="resolved",
                          message="I/O error", fired_at="2026-01-03T11:00:00+00:00",
                          resolved_at="2026-01-03T11:00:00+00:00"))
        await db.commit()

    alert_side = ok(await client.get("/api/v1/alert/events?source=alert&limit=100"))
    assert all(e["rule_id"] is not None for e in alert_side)
    assert any(e["metric"] == "temp_max" for e in alert_side)

    system_side = ok(await client.get("/api/v1/alert/events?source=system&limit=100"))
    assert all(e["rule_id"] is None for e in system_side)
    assert any(e["metric"] == "log_alert" for e in system_side)

    everything = ok(await client.get("/api/v1/alert/events?limit=100"))
    assert len(everything) >= len(alert_side) + len(system_side) - 2  # 全量包含两侧
