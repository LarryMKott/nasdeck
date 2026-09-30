"""数据库初始化：建表 + 开发期结构自愈。

SQLite 无独立迁移服务；结构演进阶段（模型加列等）create_all 不会改动已存在的旧表，
导致「no such column」类错误。此处启动时校验已知表的关键列，不符即整库重建
（开发阶段数据可弃；未来正式部署前替换为 Alembic 迁移）。
"""

from __future__ import annotations

import logging

from sqlalchemy import text

from app.db.base import Base
from app.db.session import engine

logger = logging.getLogger(__name__)

# 表名 → 建表即有的关键列（用于识别陈旧结构）
_REQUIRED_COLUMNS = {
    "metric_points": {"ts", "granularity", "cpu"},
    "alert_events": {"rule_id", "status", "fired_at", "created_at"},
    "fan_zones": {"mode", "curve_id", "created_at"},
    "alert_channels": {"config", "created_at"},
}


async def _stale_tables(conn) -> list[str]:
    stale = []
    for table, columns in _REQUIRED_COLUMNS.items():
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND :name IN (name)"),
            {"name": table},
        )
        if result.scalar() is None:
            continue  # 表不存在 → create_all 会新建
        cols = {row[1] for row in await conn.execute(text(f"PRAGMA table_info({table})"))}
        if not columns.issubset(cols):
            stale.append(table)
    return stale


async def init_db() -> None:
    from app.models import alert, control, metrics, storage, system  # noqa: F401 注册表

    async with engine.begin() as conn:
        stale = await _stale_tables(conn)
        if stale:
            logger.warning("检测到旧结构表 %s，整库重建（开发期数据可弃）", stale)
            await conn.execute(text("PRAGMA foreign_keys = OFF"))
            for table in [
                "alert_events", "alert_channels", "alert_rules",
                "fan_zones", "fan_curves", "metric_points",
                "hardware_items", "disk_aliases", "port_aliases",
                "kill_whitelist", "system_settings",
            ]:
                await conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
        await conn.run_sync(Base.metadata.create_all)
    logger.info("数据库初始化完成")
