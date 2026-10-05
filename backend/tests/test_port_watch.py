"""监听端口异动监视回归：首轮基线、新端口告警、白名单排除、24h 去重。"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.alert import AlertEvent  # noqa: F401 先于 create_all 注册 metadata
from app.models.system import PortAlias
from app.services.system import port_watch


@pytest.fixture(autouse=True)
def _reset():
    port_watch.reset_for_test()
    yield
    port_watch.reset_for_test()


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


def _listen(ports: dict[int, str]) -> set:
    """{port: proto} → psutil 风格集合替身。"""
    return {(proto, port) for port, proto in ports.items()}


async def test_first_round_baseline_only(db, monkeypatch):
    monkeypatch.setattr(port_watch, "_current_listen", lambda: _listen({8080: "tcp", 53: "udp"}))
    assert await port_watch.watch_tick(db) == []  # 首轮基线：存量监听不轰炸


async def test_new_listen_alerts_and_excludes_known(db, monkeypatch):
    seq = [
        _listen({8080: "tcp"}),
        _listen({8080: "tcp", 9999: "tcp"}),   # 新端口 → 告警
        _listen({8080: "tcp", 9999: "tcp", 53: "udp"}),
    ]
    monkeypatch.setattr(port_watch, "_current_listen", lambda: seq.pop(0))
    async with db:
        db.add(PortAlias(port=53, label="DNS"))
        await db.commit()

    assert await port_watch.watch_tick(db) == []
    events = await port_watch.watch_tick(db)
    assert events == [{"proto": "tcp", "port": 9999}]
    assert await port_watch.watch_tick(db) == []  # 53 已标注：白名单排除


async def test_dedup_window(db, monkeypatch):
    seq = [
        _listen({}),
        _listen({7000: "tcp"}),
        _listen({}),               # 端口关闭
        _listen({7000: "tcp"}),    # 24h 内重开 → 去重不告警
    ]
    monkeypatch.setattr(port_watch, "_current_listen", lambda: seq.pop(0))

    await port_watch.watch_tick(db)  # 基线（空）
    events = await port_watch.watch_tick(db)
    assert events == [{"proto": "tcp", "port": 7000}]
    assert await port_watch.watch_tick(db) == []  # 关闭：无事件
    assert await port_watch.watch_tick(db) == []  # 重开：去重窗内


async def test_persist_and_notify(db):
    from sqlalchemy import select

    from app.services.alert import engine as alert_engine

    alert_engine._pending.clear()
    await port_watch.persist_and_notify(db, [{"proto": "tcp", "port": 7000}])
    await db.commit()
    events = (await db.execute(select(AlertEvent).where(AlertEvent.metric == "port_new"))).scalars().all()
    assert len(events) == 1
    assert events[0].value == 7000.0 and events[0].severity == "warning"
    assert "7000" in events[0].message
    assert alert_engine._pending == []  # 无启用渠道时队列为空
