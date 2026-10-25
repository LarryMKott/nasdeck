"""数据库结构演进：metric_points 索引幂等收敛（历史库迁移路径）。"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.init_db import _reconcile_metric_indexes


@pytest.mark.asyncio
async def test_reconcile_metric_indexes_idempotent(tmp_path):
    """旧库的 ts/granularity 单列索引收敛到 (granularity, ts) 复合索引；可重复执行。"""
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'old.db').as_posix()}")
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "CREATE TABLE metric_points ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, ts VARCHAR(20), granularity VARCHAR(4))"
            )
        )
        await conn.execute(text("CREATE INDEX ix_metric_points_ts ON metric_points (ts)"))
        await conn.execute(
            text("CREATE INDEX ix_metric_points_granularity ON metric_points (granularity)")
        )
        await _reconcile_metric_indexes(conn)
        await _reconcile_metric_indexes(conn)  # 幂等重跑不抛错
    async with engine.connect() as conn:
        rows = await conn.execute(text("PRAGMA index_list(metric_points)"))
        names = {r[1] for r in rows}
    await engine.dispose()
    assert "ix_metric_points_gran_ts" in names
    assert not ({"ix_metric_points_ts", "ix_metric_points_granularity"} & names)


@pytest.mark.asyncio
async def test_stale_rebuild_backs_up_and_marks(tmp_path, monkeypatch):
    """通用 stale 检测（白名单外表也命中）→ 备份 → 重建 → db_rebuilt_at 标记（B4）。"""
    from sqlalchemy import inspect
    from sqlalchemy.ext.asyncio import async_sessionmaker

    import app.db.init_db as init_db_mod
    import app.db.session as session_mod
    from app.core.config import settings
    from app.models.system import SystemSetting

    db_file = tmp_path / "t.db"
    url = f"sqlite+aiosqlite:///{db_file.as_posix()}"
    monkeypatch.setattr(settings, "db_url", url)
    monkeypatch.setattr(settings, "db_allow_rebuild", True)
    test_engine = create_async_engine(url)
    maker = async_sessionmaker(test_engine, expire_on_commit=False)
    monkeypatch.setattr(init_db_mod, "engine", test_engine)
    monkeypatch.setattr(session_mod, "session_factory", maker)

    try:
        await init_db_mod.init_db()  # 首次建表
        # 模拟旧结构：drop 掉白名单外历史上不在 _REQUIRED_COLUMNS 的列
        async with test_engine.begin() as conn:
            await conn.exec_driver_sql("ALTER TABLE fan_zones DROP COLUMN chip_path")
        await init_db_mod.init_db()  # 检测 → 备份 → 重建

        assert list(tmp_path.glob("t.db.bak.*")), "重建前必须留下备份文件"
        async with maker() as db:
            row = await db.get(SystemSetting, init_db_mod.REBUILD_MARKER_KEY)
            assert row is not None and "备份" in str(row.value)

        def _cols(sync_conn):
            return {c["name"] for c in inspect(sync_conn).get_columns("fan_zones")}

        async with test_engine.connect() as conn:
            cols = await conn.run_sync(_cols)
        assert "chip_path" in cols  # 重建后结构恢复
    finally:
        await test_engine.dispose()


@pytest.mark.asyncio
async def test_rebuild_switch_off_refuses_to_start(tmp_path, monkeypatch):
    """NASDECK_DB_ALLOW_REBUILD=false：检测到旧结构拒绝重建并中止。"""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    import app.db.init_db as init_db_mod
    from app.core.config import settings

    db_file = tmp_path / "t2.db"
    url = f"sqlite+aiosqlite:///{db_file.as_posix()}"
    monkeypatch.setattr(settings, "db_url", url)
    monkeypatch.setattr(settings, "db_allow_rebuild", False)
    test_engine = create_async_engine(url)
    monkeypatch.setattr(init_db_mod, "engine", test_engine)

    try:
        await init_db_mod.init_db()
        async with test_engine.begin() as conn:
            await conn.exec_driver_sql("ALTER TABLE fan_zones DROP COLUMN chip_path")
        with pytest.raises(RuntimeError, match="ALLOW_REBUILD"):
            await init_db_mod.init_db()
    finally:
        await test_engine.dispose()
