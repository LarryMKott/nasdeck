"""安全关键链路测试：分级鉴权（require_trim_auth）+ 告警引擎状态机（evaluate_tick）。"""

from __future__ import annotations

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
