"""webhook 渠道单测：validate 校验与 send 请求（MockTransport，不打真实网络）。"""

from __future__ import annotations

import asyncio
import ipaddress

import httpx
import pytest

from app.core.exceptions import InvalidParamsError
from app.services.alert import engine
from app.services.alert.channels import webhook as webhook_mod
from app.services.alert.channels.base import CHANNEL_TYPES
from app.services.alert.channels.bark import BarkChannel
from app.services.alert.channels.email import EmailChannel
from app.services.alert.channels.webhook import WebhookChannel
from app.utils import net_guard

# DNS stub：域名一律解析到公网 IP 保持离线；字面量 IP 原样返回（SSRF 用例靠它测禁段）
_PUBLIC_IP = ipaddress.ip_address("93.184.216.34")


def _stub_resolve(host: str) -> list:
    if host.lower() == "localhost":  # 与真实 DNS 行为一致：localhost → 回环
        return [ipaddress.ip_address("127.0.0.1")]
    try:
        return [ipaddress.ip_address(host)]
    except ValueError:
        return [_PUBLIC_IP]


@pytest.fixture(autouse=True)
def _offline_dns(monkeypatch):
    monkeypatch.setattr(net_guard, "_resolve_all", _stub_resolve)


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


# ------------------------------------------------------------ SSRF 护栏（P0-B）

@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:9000/hook",        # 回环（字面量，不走 DNS stub）
        "http://localhost/hook",
        "http://10.0.0.5/hook",              # RFC1918
        "http://192.168.1.10:8080/hook",
        "http://169.254.169.254/latest/meta-data/",  # 云元数据（链路本地）
        "http://100.64.0.1/hook",            # CGNAT
        "http://[::1]/hook",                 # IPv6 回环
        "http://0.0.0.0/hook",               # unspecified
    ],
)
def test_validate_rejects_non_public_url(url):
    with pytest.raises(InvalidParamsError):
        WebhookChannel().validate({"url": url})


def test_validate_rejects_domain_resolving_to_private(monkeypatch):
    # 域名解析到私网（DNS rebinding / 内网域名）同样拒绝
    monkeypatch.setattr(net_guard, "_resolve_all", lambda host: [ipaddress.ip_address("192.168.0.9")])
    with pytest.raises(InvalidParamsError):
        WebhookChannel().validate({"url": "https://intranet.example.com/hook"})


def test_send_rejects_private_url_without_network(monkeypatch):
    # 发送时复检：内网目标在发起 HTTP 前即被拒（handler 若被调用则测试失败）
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("不应发起对内网地址的请求")

    _patch_transport(monkeypatch, handler)
    ok = asyncio.run(WebhookChannel().send({"url": "http://169.254.169.254/meta"}, "t", "b"))
    assert ok is False


def test_bark_validate_rejects_private_server():
    with pytest.raises(InvalidParamsError):
        BarkChannel().validate({"device_key": "k", "server": "http://192.168.1.4:8080"})


def test_bark_validate_ok_with_default_server():
    BarkChannel().validate({"device_key": "k"})


def test_email_validate_rejects_private_host():
    with pytest.raises(InvalidParamsError):
        EmailChannel().validate(
            {"host": "127.0.0.1", "port": 25, "username": "u", "password": "p", "to": "a@b.com"}
        )


def test_email_validate_rejects_bad_port():
    with pytest.raises(InvalidParamsError):
        EmailChannel().validate(
            {"host": "smtp.example.com", "port": "abc", "username": "u", "password": "p", "to": "a@b.com"}
        )


def test_email_send_rejects_private_host_without_smtp():
    # port 非数字/内网 host 在连 SMTP 前被拒，send 不抛异常且返回 False
    ok = asyncio.run(
        EmailChannel().send(
            {"host": "10.0.0.5", "port": "not-a-port", "username": "u", "password": "p", "to": "a@b.com"},
            "t",
            "b",
        )
    )
    assert ok is False
