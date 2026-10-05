"""容器退出检测回归：状态对比、首轮基线、去重窗、删除清理、落库与广播。"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.alert import AlertEvent
from app.services.alert import engine as alert_engine
from app.services.system import docker_watch


def _states(*entries: tuple[str, str, str]) -> dict[str, dict]:
    """(cid, state, name) → docker ps -a 形态。"""
    return {
        cid: {"name": name, "state": state, "status": f"state={state}"}
        for cid, state, name in entries
    }


async def _fake_states(result):
    """list_all_states 异步替身（watch_tick 内 await）。"""
    return result


@pytest.fixture(autouse=True)
def _reset():
    docker_watch.reset_for_test()
    alert_engine._pending.clear()
    yield
    docker_watch.reset_for_test()
    alert_engine._pending.clear()


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


async def test_first_round_baseline_only(monkeypatch):
    monkeypatch.setattr(docker_watch.docker, "list_all_states",
                        lambda: _fake_states(_states(("a" * 12, "running", "plex"), ("b" * 12, "exited", "old"))))
    assert await docker_watch.watch_tick() == []  # 首轮只建基线：存量退出容器不轰炸


async def test_exit_transition_alerts_and_dedups(monkeypatch):
    seq = [
        _states(("a" * 12, "running", "plex")),
        _states(("a" * 12, "exited", "plex")),
        _states(("a" * 12, "running", "plex")),  # 重启
        _states(("a" * 12, "exited", "plex")),   # 1h 内再次退出 → 去重
    ]
    monkeypatch.setattr(docker_watch.docker, "list_all_states", lambda: _fake_states(seq.pop(0)))

    assert await docker_watch.watch_tick() == []
    events = await docker_watch.watch_tick()
    assert len(events) == 1 and events[0]["name"] == "plex"
    assert await docker_watch.watch_tick() == []  # running 不告警
    assert await docker_watch.watch_tick() == []  # 去重窗内


async def test_new_exited_container_not_alerted(monkeypatch):
    seq = [
        _states(("a" * 12, "running", "plex")),
        _states(("a" * 12, "running", "plex"), ("b" * 12, "exited", "tmp")),  # 新出现即退出：非转换
    ]
    monkeypatch.setattr(docker_watch.docker, "list_all_states", lambda: _fake_states(seq.pop(0)))
    await docker_watch.watch_tick()
    assert await docker_watch.watch_tick() == []


async def test_docker_unavailable_returns_empty(monkeypatch):
    monkeypatch.setattr(docker_watch.docker, "list_all_states", lambda: _fake_states(None))
    assert await docker_watch.watch_tick() == []


async def test_persist_and_notify(db):
    alert_engine._pending.clear()
    exits = [{"cid": "a" * 12, "name": "plex", "status": "exited (137)"}]
    await docker_watch.persist_and_notify(db, exits)
    await db.commit()

    events = (await db.execute(select(AlertEvent).where(AlertEvent.metric == "docker_exit"))).scalars().all()
    assert len(events) == 1
    e = events[0]
    assert e.rule_name == "容器退出" and e.status == "resolved" and e.severity == "warning"
    assert "plex" in e.message and "137" in e.message
    # 渠道为空时通知队列为空（有渠道时逐启用渠道入队）
    assert alert_engine._pending == []
