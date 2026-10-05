"""数据库初始化：建表 + 开发期结构自愈。

SQLite 无独立迁移服务；结构演进阶段（模型加列等）create_all 不会改动已存在的旧表，
导致「no such column」类错误。此处启动时经 SQLAlchemy 检查器校验已知表的关键列，
不符即整库重建（开发阶段数据可弃；未来正式部署前替换为 Alembic 迁移）。
全程用检查器/metadata/Index DDL 元素表达，不写裸 SQL——连接 PRAGMA 是唯一豁免
（驱动层配置，SQLAlchemy 无对应抽象），集中在 db/session.py。
"""

from __future__ import annotations

import logging

from sqlalchemy import Index, inspect
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.base import Base
from app.db.session import engine
from app.models.metrics import MetricPoint

logger = logging.getLogger(__name__)

# 表名 → 建表即有的关键列（用于识别陈旧结构）
_REQUIRED_COLUMNS = {
    "metric_points": {"ts", "granularity", "cpu"},
    "alert_events": {"rule_id", "status", "fired_at", "created_at"},
    "fan_zones": {"mode", "curve_id", "created_at"},
    "alert_channels": {"config", "created_at"},
    "smart_points": {"ts", "granularity", "device", "metric"},
    "volume_points": {"ts", "mount", "used_gb"},
    # actions 列（M2.1 剧本动作）：旧表缺列 → 触发整库重建（开发期约定）
    "alert_rules": {"name", "metric", "actions"},
}

# 重建白名单：仅登记过的表可被整库重建
_REBUILD_TABLES = (
    "alert_events", "alert_channels", "alert_rules",
    "fan_zones", "fan_curves", "metric_points",
    "hardware_items", "disk_aliases", "port_aliases",
    "kill_whitelist", "system_settings", "smart_points", "volume_points",
)

# 历史版本建过、已从模型移除的 metric_points 单列索引
_LEGACY_METRIC_INDEXES = ("ix_metric_points_ts", "ix_metric_points_granularity")


async def _stale_tables(conn: AsyncConnection) -> list[str]:
    """对照 _REQUIRED_COLUMNS 找出关键列缺失的旧结构表（经检查器，无裸 SQL）。"""

    def _check(sync_conn) -> list[str]:
        insp = inspect(sync_conn)
        stale = []
        for table, columns in _REQUIRED_COLUMNS.items():
            if not insp.has_table(table):
                continue  # 表不存在 → create_all 会新建
            cols = {c["name"] for c in insp.get_columns(table)}
            if not columns.issubset(cols):
                stale.append(table)
        return stale

    return await conn.run_sync(_check)


def _reconcile_metric_indexes_sync(sync_conn) -> None:
    """metric_points 索引幂等收敛（同步侧，供 run_sync 调度）。

    create_all 对已存在的表整体跳过：模型新增的索引不会补建，历史版本遗留的
    单列索引（ts 被 uq 前缀覆盖、granularity 仅 3 个值）也需清理。按检查器
    existing 集合 diff 出要删/建的索引，经 Index DDL 元素执行。
    """
    insp = inspect(sync_conn)
    table = MetricPoint.__table__
    existing = {ix["name"] for ix in insp.get_indexes(table.name)}
    for name in _LEGACY_METRIC_INDEXES:
        if name not in existing:
            continue
        idx = Index(name, table.columns["ts"])
        table.indexes.discard(idx)  # 借道构造 DDL 即弃：留在 metadata 会被 create_all 复活
        idx.drop(sync_conn)
    for idx in table.indexes:
        if idx.name not in existing:
            idx.create(sync_conn)


async def _reconcile_metric_indexes(conn: AsyncConnection) -> None:
    await conn.run_sync(_reconcile_metric_indexes_sync)


async def init_db() -> None:
    # 显式导入全部模型模块注册 metadata（models/__init__ 为空，不导入的模块其表
    # 不会进入 Base.metadata——此前 hardware 漏注册，重建分支一跑即 KeyError）
    from app.models import alert, control, hardware, storage, system  # noqa: F401 注册表

    async with engine.begin() as conn:
        stale = await _stale_tables(conn)
        if stale:
            logger.warning("检测到旧结构表 %s，整库重建（开发期数据可弃）", stale)

            def _rebuild(sync_conn) -> None:
                # 防御性过滤：未注册进 metadata 的名字跳过（正常应全部命中）
                tables = [Base.metadata.tables[n] for n in _REBUILD_TABLES if n in Base.metadata]
                # drop_all 按 metadata 依赖序删除；SQLite 外键默认不启用（session 也未开启），
                # 无需像旧实现那样先 PRAGMA foreign_keys = OFF
                Base.metadata.drop_all(sync_conn, tables=tables, checkfirst=True)

            await conn.run_sync(_rebuild)
        await conn.run_sync(Base.metadata.create_all)
        await _reconcile_metric_indexes(conn)
    logger.info("数据库初始化完成")
