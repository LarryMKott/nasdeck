"""一键体检单测：六维聚合装配、缺数据降级与总分（花活二期 N）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.alert import AlertEvent
from app.services.monitor import checkup
from tests.conftest import ok


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.fixture(autouse=True)
def _no_hardware(monkeypatch):
    """屏蔽真机差异：盘清单空、温度无源、storcli/mdstat 探测照常（Windows 下自然为空）。"""
    from app.services.storage import volumes as volume_service

    async def _no_disks():
        return []

    monkeypatch.setattr(volume_service, "list_disks", _no_disks)


async def test_checkup_shape_and_missing_data(db):
    """空库空硬件：全项装配不炸；缺数据项 score=null/status=warn（不造假）。"""
    r = await checkup.run_checkup(db)
    keys = [i["key"] for i in r["items"]]
    assert keys == list(checkup.ITEM_KEYS)
    by_key = {i["key"]: i for i in r["items"]}
    assert by_key["oracle"]["score"] is None and by_key["oracle"]["status"] == "warn"
    assert by_key["temp"]["score"] is None and by_key["temp"]["status"] == "warn"
    assert by_key["raid"]["score"] == 100.0  # 无阵列 = 直连盘，非缺数据
    assert r["score"] is not None  # 其余维度可加权出总分
    assert r["grade"] in ("ok", "warn", "bad")


async def test_checkup_alert_penalty(db):
    now = datetime.now(UTC)
    for i in range(3):
        db.add(
            AlertEvent(
                rule_id=None,
                rule_name="r",
                metric="temp_max",
                severity="warning",
                status="resolved",
                fired_at=(now - timedelta(days=i + 1)).strftime("%Y-%m-%dT%H:%M:%S"),
            )
        )
    db.add(
        AlertEvent(
            rule_id=None,
            rule_name="r",
            metric="temp_max",
            severity="critical",
            status="resolved",
            fired_at=now.strftime("%Y-%m-%dT%H:%M:%S"),
        )
    )
    await db.commit()
    r = await checkup.run_checkup(db)
    alerts = next(i for i in r["items"] if i["key"] == "alerts")
    assert alerts["score"] == 81.0  # 100 - 1×10(严重) - 3×3(警告)
    assert "1 严重" in alerts["detail"]
    assert alerts["detail"].startswith("30 天 4 条")


async def test_checkup_api(client):
    """response_model 过滤回归锁：/monitor/checkup 透出 items/score/grade。"""
    r = ok(await client.get("/api/v1/monitor/checkup"))
    assert set(r.keys()) >= {"items", "score", "grade"}
    assert len(r["items"]) == 6
