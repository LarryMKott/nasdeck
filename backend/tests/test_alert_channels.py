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
