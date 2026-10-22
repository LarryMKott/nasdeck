"""访问模型（CGI 反代 / 统一网关）后端形态测试。

网关形态 = NASDECK_UDS 监听 Unix Socket + NASDECK_GATEWAY_PREFIX 前缀剥离 +
不注入代理密钥（信任边界为 socket 文件权限）；CGI 形态 = TCP 回环 + proxy_token
信任链。本文件锁三件事：前缀剥离对 http 生效且无前缀时透传、index.html 资源基址
占位符按 NASDECK_PUBLIC_PATH 一次性替换（幂等）、鉴权在 UDS 形态免代理头而 CGI
形态必需。
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from app.core.config import settings
from app.core.dependencies import require_trim_auth
from app.core.exceptions import PermissionDeniedError
from app.core.statics import mount_spa
from main import create_app

GW_PREFIX = "/app/com.dashboard.nasdeck"


def _request(method: str, headers: dict[str, str]) -> Request:
    """构造最小 Request（依赖只读 method 与 headers）。"""
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "method": method, "headers": raw, "query_string": b""})


async def test_gateway_prefix_strip(monkeypatch):
    """网关前缀剥离：/app/{app}/x → /x 进路由；未剥离形态无法命中判别路由。"""
    monkeypatch.setattr(settings, "gateway_prefix", GW_PREFIX)
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        body = (await ac.get(f"{GW_PREFIX}/health")).json()
        assert body["code"] == 0 and body["data"] == {"status": "healthy"}
        # 剥离生效的判别路由：openapi.json 注册在 /openapi.json，不剥前缀必 404
        assert (await ac.get(f"{GW_PREFIX}/openapi.json")).status_code == 200
        # API 前缀语义保持：剥离后未注册路径仍是 404（而非前缀导致的 404 混淆）
        assert (await ac.get(f"{GW_PREFIX}/api/v1/nonexistent")).status_code == 404


async def test_gateway_prefix_absent_passthrough(monkeypatch):
    """CGI/直连形态（gateway_prefix 空）：不挂剥离中间件，行为与历史版本一致。"""
    monkeypatch.setattr(settings, "gateway_prefix", "")
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        assert (await ac.get("/openapi.json")).status_code == 200


def test_public_path_placeholder_rewrite(tmp_path, monkeypatch):
    """占位符按 NASDECK_PUBLIC_PATH 一次性替换落盘（index.html + JS 动态 import + CSS）。"""
    dist = tmp_path / "dist"
    (dist / "assets" / "js").mkdir(parents=True)
    (dist / "assets" / "css").mkdir(parents=True)
    original_html = '<script src="/__ND_PREFIX__/assets/a.js"></script><link href="/__ND_PREFIX__/x.css">'
    (dist / "index.html").write_text(original_html, encoding="utf-8")
    # vite 把 base 烤进 JS 的懒加载 import 路径——只改 index.html 会让懒加载 chunk 全 404
    (dist / "assets" / "js" / "views.js").write_text(
        'const v="/__ND_PREFIX__/assets/js/NotFoundView-n2AIIAV0.js"', encoding="utf-8"
    )
    (dist / "assets" / "css" / "x.css").write_text(
        'body{background:url("/__ND_PREFIX__/assets/img/bg.png")}', encoding="utf-8"
    )
    monkeypatch.setattr(settings, "public_path", "/cgi/ThirdParty/com.dashboard.nasdeck/index.cgi")

    mount_spa(FastAPI(), str(dist))
    expect = "/cgi/ThirdParty/com.dashboard.nasdeck/index.cgi"
    assert f'src="{expect}/assets/a.js"' in (dist / "index.html").read_text(encoding="utf-8")
    assert f'const v="{expect}/assets/js/NotFoundView-n2AIIAV0.js"' in (
        dist / "assets" / "js" / "views.js"
    ).read_text(encoding="utf-8")
    assert f'url("{expect}/assets/img/bg.png")' in (dist / "assets" / "css" / "x.css").read_text(
        encoding="utf-8"
    )
    # 幂等：占位符已消失，重复挂载不再改动（升级重启场景）
    mount_spa(FastAPI(), str(dist))
    assert "__ND_PREFIX__" not in (dist / "index.html").read_text(encoding="utf-8")
    assert "__ND_PREFIX__" not in (dist / "assets" / "js" / "views.js").read_text(encoding="utf-8")


def test_public_path_empty_leaves_dist_untouched(tmp_path, monkeypatch):
    """开发/自托管直连形态（public_path 空）：产物即最终形态，不改动。"""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text('<script src="/__ND_PREFIX__/a.js"></script>', encoding="utf-8")
    monkeypatch.setattr(settings, "public_path", "")

    mount_spa(FastAPI(), str(dist))
    assert '<script src="/__ND_PREFIX__/a.js"></script>' == (dist / "index.html").read_text(encoding="utf-8")


async def test_uds_mode_skips_proxy_token_keeps_identity(monkeypatch):
    """网关形态：无代理密钥头但有登录身份 → 放行（边界=socket 权限）；非 GET 仍需管理员。"""
    monkeypatch.setattr(settings, "trim_auth", True)
    monkeypatch.setattr(settings, "proxy_token", "secret")
    monkeypatch.setattr(settings, "uds", "/var/apps/com.dashboard.nasdeck/target/app.sock")

    await require_trim_auth(_request("GET", {"X-Trim-Userid": "1000"}))  # 不抛即放行
    with pytest.raises(PermissionDeniedError):
        await require_trim_auth(_request("POST", {"X-Trim-Userid": "1000"}))  # 缺管理员
    await require_trim_auth(
        _request("POST", {"X-Trim-Userid": "1000", "X-Trim-Isadmin": "true"})
    )


async def test_cgi_mode_still_requires_proxy_token(monkeypatch):
    """CGI 形态回归锁：proxy_token 配置存在时，无 X-Nasdeck-Proxy 一律 403。"""
    monkeypatch.setattr(settings, "trim_auth", True)
    monkeypatch.setattr(settings, "proxy_token", "secret")
    monkeypatch.setattr(settings, "uds", "")

    with pytest.raises(PermissionDeniedError):
        await require_trim_auth(_request("GET", {"X-Trim-Userid": "1000"}))
    await require_trim_auth(_request("GET", {"X-Trim-Userid": "1000", "X-Nasdeck-Proxy": "secret"}))
