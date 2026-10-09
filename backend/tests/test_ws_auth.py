"""WS 实时推送鉴权测试（T2/S3）+ REST 代理密钥 fail-closed 端到端（S2/T10）。

此前 /api/v1/ws/realtime 完全裸奔（被误删不会变红），本文件锁定：
- trim 形态：先 fail-closed 验 X-Nasdeck-Proxy（未配置即拒），再验 X-Trim-Userid；
- api_key 形态：?api_key 查询参数经 hmac.compare_digest 校验；
- REST 侧：proxy_token 为空时一律 403/1004，不存在"未配置则跳过"的降级路径。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

try:  # 老版 TestClient 经 websockets 客户端握手时可能抛 InvalidData，与 Disconnect 同等视为拒绝
    from websockets.exceptions import InvalidData
except ImportError:  # 本仓库 venv 未装 websockets：TestClient 走原生 ASGI 接口，只会抛 Disconnect
    InvalidData = None

from tests.conftest import err, ok

WS_PATH = "/api/v1/ws/realtime"
_REJECT_ERRORS: tuple = (WebSocketDisconnect, InvalidData) if InvalidData else (WebSocketDisconnect,)


@pytest.fixture
def ws_client():
    from main import app

    return TestClient(app)


def _assert_rejected(client, headers: dict | None = None, url: str = WS_PATH) -> None:
    """握手必须被拒（close 1008）；若 accept 成功则用例直接失败。"""
    with pytest.raises(_REJECT_ERRORS) as ei:
        with client.websocket_connect(url, headers=headers or {}):
            raise AssertionError("鉴权应拒绝握手，不应进入连接上下文")
    code = getattr(ei.value, "code", None)
    if code is not None:  # InvalidData 无 code 字段，跳过
        assert code == 1008


def _assert_accepted(client, headers: dict | None = None, url: str = WS_PATH) -> None:
    """握手放行即可（accept 后立即断开，不消费推送流）。"""
    with client.websocket_connect(url, headers=headers or {}):
        pass


# ---------------- trim 形态：代理密钥根防线 + 身份头（S3） ----------------


def test_ws_trim_requires_proxy_and_identity(ws_client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "trim_auth", True, raising=False)
    monkeypatch.setattr(settings, "proxy_token", "tok", raising=False)

    _assert_rejected(ws_client)  # 无头直连：本机进程不得绕过 CGI 反代拉数据
    _assert_rejected(ws_client, headers={"X-Nasdeck-Proxy": "wrong", "X-Trim-Userid": "u1"})
    _assert_accepted(ws_client, headers={"X-Nasdeck-Proxy": "tok", "X-Trim-Userid": "u1"})


def test_ws_trim_fail_closed_without_proxy_token(ws_client, monkeypatch):
    """trim_auth=True 且 proxy_token=""：带齐身份头也必须拒——不存在放行路径。"""
    from app.core.config import settings

    monkeypatch.setattr(settings, "trim_auth", True, raising=False)
    monkeypatch.setattr(settings, "proxy_token", "", raising=False)

    _assert_rejected(ws_client)
    _assert_rejected(ws_client, headers={"X-Nasdeck-Proxy": "tok", "X-Trim-Userid": "u1"})


# ---------------- api_key 形态：查询参数常数时间校验（S3） ----------------


def test_ws_api_key_mode(ws_client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "trim_auth", False, raising=False)
    monkeypatch.setattr(settings, "api_key", "k1", raising=False)

    _assert_accepted(ws_client, url=f"{WS_PATH}?api_key=k1")
    _assert_rejected(ws_client, url=f"{WS_PATH}?api_key=wrong")
    _assert_rejected(ws_client)  # 缺失参数


# ---------------- REST fail-closed（S2）+ 端到端接线（T10） ----------------


async def test_rest_fail_closed_without_proxy_token(client, monkeypatch):
    """trim_auth=True、proxy_token=""：全部请求 403/1004，信任链不得静默退化。"""
    from app.core.config import settings

    monkeypatch.setattr(settings, "trim_auth", True, raising=False)
    monkeypatch.setattr(settings, "proxy_token", "", raising=False)
    monkeypatch.setattr(settings, "api_key", "", raising=False)

    resp = await client.get("/api/v1/system/info")
    err(resp, 1004)
    assert resp.status_code == 403


async def test_rest_trim_proxy_gate_and_admin_levels(client, monkeypatch):
    """proxy_token=tok：无代理密钥一律拒；读须登录；写须管理员（真实 HTTP 接线）。"""
    from app.core.config import settings

    monkeypatch.setattr(settings, "trim_auth", True, raising=False)
    monkeypatch.setattr(settings, "proxy_token", "tok", raising=False)
    monkeypatch.setattr(settings, "api_key", "", raising=False)

    user = {"X-Nasdeck-Proxy": "tok", "X-Trim-Userid": "u1"}
    admin = {"X-Nasdeck-Proxy": "tok", "X-Trim-Userid": "1", "X-Trim-Isadmin": "true"}

    # 身份头单独存在但无代理密钥 → 仍拒（代理密钥是根防线，防本机进程伪造身份头）
    resp = await client.get("/api/v1/system/info", headers={"X-Trim-Userid": "u1"})
    err(resp, 1004)
    assert resp.status_code == 403

    # 正确代理头 + 身份头 → 读放行
    ok(await client.get("/api/v1/system/info", headers=user))

    # 非管理员写 → 403/1004
    resp = await client.delete("/api/v1/system/whitelist/999", headers=user)
    err(resp, 1004)
    assert resp.status_code == 403

    # 管理员写 → 鉴权通过，业务层资源不存在（1001，而非 1004）
    resp = await client.delete("/api/v1/system/whitelist/999", headers=admin)
    err(resp, 1001)
    assert resp.status_code == 404
