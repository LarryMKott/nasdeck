"""安全关键链路测试：分级鉴权（require_trim_auth）+ 告警引擎状态机（evaluate_tick）。"""

from __future__ import annotations

import contextlib

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.dependencies import require_trim_auth
from app.core.exceptions import PermissionDeniedError
from app.db.base import Base
from app.models.alert import AlertRule
from app.services.alert import engine

# ---------------- 分级鉴权（铁律：设置/写操作仅管理员） ----------------


class _Req:
    def __init__(self, headers: dict | None = None, method: str = "GET"):
        self.headers = headers or {}
        self.method = method


@pytest.fixture
def trim_on(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "trim_auth", True, raising=False)
    monkeypatch.setattr(settings, "proxy_token", "", raising=False)


@pytest.mark.asyncio
async def test_trim_off_allows_anonymous(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "trim_auth", False, raising=False)
    await require_trim_auth(_Req())  # 不抛即通过


@pytest.mark.asyncio
async def test_trim_requires_userid_for_read(trim_on):
    with pytest.raises(PermissionDeniedError):
        await require_trim_auth(_Req())
    await require_trim_auth(_Req({"X-Trim-Userid": "1000"}))


@pytest.mark.asyncio
async def test_trim_write_requires_admin(trim_on):
    user = {"X-Trim-Userid": "1000", "X-Trim-Isadmin": "false"}
    with pytest.raises(PermissionDeniedError):
        await require_trim_auth(_Req(user, method="POST"))
    admin = {"X-Trim-Userid": "1", "X-Trim-Isadmin": "true"}
    await require_trim_auth(_Req(admin, method="POST"))
    await require_trim_auth(_Req(admin, method="DELETE"))


@pytest.mark.asyncio
async def test_proxy_token_is_root_defense(monkeypatch):
    """身份头可被任意本机请求伪造，代理密钥证明其来自持密的 index.cgi。"""
    from app.core.config import settings

    monkeypatch.setattr(settings, "trim_auth", True, raising=False)
    monkeypatch.setattr(settings, "proxy_token", "s3cret", raising=False)
    admin = {"X-Trim-Userid": "1", "X-Trim-Isadmin": "true"}

    with pytest.raises(PermissionDeniedError):
        await require_trim_auth(_Req(admin, method="POST"))  # 无密钥：即使管理员头也被拒
    with pytest.raises(PermissionDeniedError):
        await require_trim_auth(_Req({**admin, "X-Nasdeck-Proxy": "wrong"}, method="POST"))
    await require_trim_auth(_Req({**admin, "X-Nasdeck-Proxy": "s3cret"}, method="POST"))


# ---------------- WS 鉴权与连接韧性（评审 2026-10-25 P1-01 / P1-9） ----------------


def _ws_settings(monkeypatch, trim: bool, token: str = ""):
    from app.core.config import settings

    monkeypatch.setattr(settings, "trim_auth", trim, raising=False)
    monkeypatch.setattr(settings, "proxy_token", token, raising=False)
    monkeypatch.setattr(settings, "api_key", "", raising=False)
    return settings


def _ws_app():
    """裸 WS app：不带 main 的 lifespan（调度器/ingest 与 TestClient portal 互扰）。"""
    from fastapi import FastAPI

    from app.api.ws.realtime import router as ws_router

    app = FastAPI()
    app.include_router(ws_router)
    return app


@contextlib.contextmanager
def _ws_session(tc, **kw):
    """WS 会话上下文：退出时吞掉 teardown 噪声。

    本机（Windows + 当前 starlette 组合）WebSocketTestSession.__exit__ 偶发
    CancelledError，新旧 handler 均可复现（与被测行为无关）；断言全部在
    会话体内完成，退出噪声不掩盖真实失败。
    """
    session = tc.websocket_connect(**kw)
    session.__enter__()
    try:
        yield session
    finally:
        try:
            session.__exit__(None, None, None)
        except Exception:  # noqa: BLE001 环境噪声，见 docstring
            pass


def test_ws_trim_form_requires_proxy_token(monkeypatch):
    """trim 形态下伪造 userid 头不足以直连：须持代理共享密钥（与 REST 同口径）。"""
    from fastapi.testclient import TestClient

    _ws_settings(monkeypatch, trim=True, token="s3cret")
    with TestClient(_ws_app()) as tc:
        # 只有 userid、无密钥 → 1008 拒绝（握手即失败）
        session = tc.websocket_connect("/api/v1/ws/realtime", headers={"x-trim-userid": "1000"})
        # starlette 握手拒绝抛 WebSocketDisconnect（RuntimeError 兜底不同版本文案）
        with pytest.raises((RuntimeError, Exception)) as ei:
            session.__enter__()
        assert not isinstance(ei.value, AssertionError)
        # 密钥 + userid → 握手通过且 ping/pong 正常（连接先补发 realtime 帧，读到 pong 为止）
        with _ws_session(
            tc, url="/api/v1/ws/realtime", headers={"x-trim-userid": "1000", "x-nasdeck-proxy": "s3cret"}
        ) as ws:
            ws.send_text("ping")
            for _ in range(50):
                if ws.receive_json() == {"type": "pong"}:
                    break
            else:
                pytest.fail("未收到 pong")


def test_ws_binary_frame_does_not_kill_handler(monkeypatch):
    """二进制帧曾被 receive_text 的 KeyError 杀死 recv 任务 → handler 永久挂起泄漏。"""
    from fastapi.testclient import TestClient

    _ws_settings(monkeypatch, trim=False, token="")
    with TestClient(_ws_app()) as tc:
        with _ws_session(tc, url="/api/v1/ws/realtime") as ws:
            ws.send_bytes(b"\x00\x01binary-noise")
            ws.send_text("ping")
            # 二进制帧被忽略后连接仍活：pong 能回到（期间可能先到 realtime 推送帧）
            for _ in range(50):
                msg = ws.receive_json()
                if msg == {"type": "pong"}:
                    break
            else:
                pytest.fail("二进制帧后未收到 pong：handler 已死")


# ---------------- 告警引擎：连击计数 / 触发 / 去重 / 恢复 ----------------


@pytest.fixture
async def db():
    engine_ = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    maker = async_sessionmaker(engine_, expire_on_commit=False)

    async def make():
        async with engine_.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        return maker

    yield make
    await engine_.dispose()


@pytest.fixture(autouse=True)
def reset_engine_state():
    engine._tick_counters.clear()
    engine._firing.clear()
    yield
    engine._tick_counters.clear()
    engine._firing.clear()


def test_compare_matrix():
    assert engine.compare(61, ">", 60) and not engine.compare(60, ">", 60)
    assert engine.compare(60, ">=", 60) and engine.compare(60, "==", 60)
    assert engine.compare(59, "<", 60) and engine.compare(60, "<=", 60)
    assert not engine.compare(1, " bogus", 60)


async def test_evaluate_tick_fire_and_resolve(db):
    maker = await db()
    async with maker() as session:
        session.add(
            AlertRule(
                name="r1",
                metric="temp_max",
                comparator=">",
                threshold=60,
                duration_ticks=2,
                severity="warning",
                channels=[],
                enabled=True,
            )
        )
        await session.flush()

        hot = {"temp_max": 65.0}
        cold = {"temp_max": 45.0}
        # 第 1 tick 命中：未达 duration_ticks，不触发
        assert await engine.evaluate_tick(session, hot) == []
        # 第 2 tick：连击达标 → firing
        events = await engine.evaluate_tick(session, hot)
        assert len(events) == 1 and events[0]["status"] == "firing"
        # 持续命中：已 firing 去重，不重复发事件
        assert await engine.evaluate_tick(session, hot) == []
        # 回落 → resolved
        events = await engine.evaluate_tick(session, cold)
        assert len(events) == 1 and events[0]["status"] == "resolved"
        assert engine._firing == {} and engine._tick_counters[1] == 0


async def test_evaluate_tick_skips_missing_metric(db):
    maker = await db()
    async with maker() as session:
        session.add(
            AlertRule(
                name="r2",
                metric="temp_max",
                comparator=">",
                threshold=10,
                duration_ticks=1,
                severity="warning",
                channels=[],
                enabled=True,
            )
        )
        await session.flush()
        # 指标无数据（None）：不评也不误触发
        assert await engine.evaluate_tick(session, {}) == []
        assert engine._firing == {}
