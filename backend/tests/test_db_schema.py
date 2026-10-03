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
