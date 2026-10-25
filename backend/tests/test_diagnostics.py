"""系统自检聚合（原型 E1）：结构、断流判定、开关量与分组完整性。"""

from __future__ import annotations

from app.services.system import diagnostics


async def test_collect_returns_all_groups_with_valid_status():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    from app.db.base import Base

    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        result = await diagnostics.collect(db)
    await engine.dispose()

    assert [g["name"] for g in result["groups"]] == ["数据管线", "风扇", "鉴权链", "采集工具", "通知"]
    valid = {"ok", "warn", "fail", "skip"}
    for group in result["groups"]:
        assert group["items"], group["name"]
        for item in group["items"]:
            assert item["status"] in valid, item
            assert item["detail"]


async def test_ingest_stall_detection_flags_when_stale(monkeypatch):
    """断流判定：last_write_ts 距今超阈值 → fail（自检页红条的数据源）。"""
    import time as _time

    from app.db import ingest as ingest_mod

    monkeypatch.setattr(
        ingest_mod, "stats",
        lambda: {
            "worker_running": True, "worker_restarts": 0, "queue_depth": 0, "queue_capacity": 600,
            "dropped_total": 0, "last_write_ts": _time.time() - 120, "last_error": None,
        },
    )
    # _check_pipeline 需要 db（读 db_rebuilt 标记），用内存库跑
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    from app.db.base import Base

    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        items = await diagnostics._check_pipeline(db)
    await engine.dispose()
    stall = next(i for i in items if i["key"] == "ingest_stall")
    assert stall["status"] == "fail" and "120" in stall["detail"]
