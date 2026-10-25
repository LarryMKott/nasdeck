"""数据库初始化：建表 + 结构自愈（备份保护版）。

SQLite 无独立迁移服务；结构演进阶段（模型加列等）create_all 不会改动已存在的
旧表，导致「no such column」类错误。此处启动时对照全部业务模型做"模型列集 ⊆
实际列集"通用检查（旧白名单漏了半数表，加列既不触发重建也不被补建——评审
2026-10-25 N5/B4），不符即整库重建。

重建安全三件套（正式部署前替换为 Alembic 迁移）：
1. NASDECK_DB_ALLOW_REBUILD=false（生产建议）时拒绝重建并中止启动；
2. 重建前备份 DB 文件（含 WAL 伴生文件），备份失败拒绝重建；
3. 重建后落 system_settings.db_rebuilt_at 标记（自检页展示）。
全程用检查器/metadata/Index DDL 元素表达，不写裸 SQL——连接 PRAGMA 是唯一豁免
（驱动层配置，SQLAlchemy 无对应抽象），集中在 db/session.py。
"""

from __future__ import annotations

import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote

from sqlalchemy import Index, inspect
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import settings
from app.db.base import Base
from app.db.session import engine
from app.models.metrics import MetricPoint

logger = logging.getLogger(__name__)

REBUILD_MARKER_KEY = "db_rebuilt_at"

# 重建白名单：仅登记过的表可被整库重建（防未来误注册非业务表）
_REBUILD_TABLES = (
    "alert_events", "alert_channels", "alert_rules",
    "fan_zones", "fan_curves", "metric_points",
    "hardware_items", "disk_aliases", "port_aliases",
    "kill_whitelist", "system_settings",
)

# 历史版本建过、已从模型移除的 metric_points 单列索引
_LEGACY_METRIC_INDEXES = ("ix_metric_points_ts", "ix_metric_points_granularity")


async def _stale_tables(conn: AsyncConnection) -> list[str]:
    """通用 stale 检测：对 metadata 中每张已存在的表，模型列集 ⊄ 实际列集即陈旧。"""

    def _check(sync_conn) -> list[str]:
        insp = inspect(sync_conn)
        stale = []
        for name, table in Base.metadata.tables.items():
            if not insp.has_table(name):
                continue  # 表不存在 → create_all 会新建
            actual = {c["name"] for c in insp.get_columns(name)}
            missing = set(table.columns.keys()) - actual
            if missing:
                stale.append(f"{name}（缺 {','.join(sorted(missing))}）")
        return stale

    return await conn.run_sync(_check)


def _db_file() -> Path | None:
    """db_url → 文件路径；:memory: / 非 sqlite 返回 None（无文件可备份）。

    兼容三斜杠带盘符（sqlite+aiosqlite:///D:/x → D:/x）与四斜杠 POSIX 绝对路径
    （sqlite+aiosqlite:////abs/path → /abs/path）两种写法。
    """
    url = settings.db_url
    if ":memory:" in url or not url.startswith("sqlite"):
        return None
    raw = url.split(":///", 1)[1] if ":///" in url else ""
    try:
        return Path(unquote(raw))
    except ValueError:
        return None


def _backup_db_file() -> Path | None:
    """备份 DB 文件（含 -wal/-shm）到 <name>.bak.<ts>；失败返回 None。"""
    src = _db_file()
    if src is None or not src.exists():
        return None  # 无文件（首启/内存库）无需备份
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    dst = src.with_name(f"{src.name}.bak.{stamp}")
    try:
        shutil.copy2(src, dst)
        for suffix in ("-wal", "-shm"):
            side = src.with_name(src.name + suffix)
            if side.exists():
                shutil.copy2(side, dst.with_name(dst.name + suffix))
    except OSError as exc:
        logger.error("DB 备份失败（%s → %s）：%s，拒绝重建", src, dst, exc)
        raise
    return dst


async def _reconcile_metric_indexes(conn: AsyncConnection) -> None:
    await conn.run_sync(_reconcile_metric_indexes_sync)


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


async def init_db() -> None:
    # 显式导入全部模型模块注册 metadata（models/__init__ 为空，不导入的模块其表
    # 不会进入 Base.metadata——此前 hardware 漏注册，重建分支一跑即 KeyError）
    from app.models import alert, control, hardware, storage, system  # noqa: F401 注册表

    async with engine.begin() as conn:
        stale = await _stale_tables(conn)

    backup_path: Path | None = None
    if stale:
        if not settings.db_allow_rebuild:
            raise RuntimeError(
                f"检测到旧结构表 {stale}，NASDECK_DB_ALLOW_REBUILD=false 禁止自动重建——"
                "请手动备份并迁移数据后删除该开关，或联系维护者（Alembic 迁移建设中）"
            )
        backup_path = _backup_db_file()  # 备份失败会抛错拒绝重建
        logger.warning(
            "检测到旧结构表 %s，已备份 %s，整库重建（历史将重新积累）", stale, backup_path or "（内存库无文件）"
        )

    async with engine.begin() as conn:
        if stale:

            def _rebuild(sync_conn) -> None:
                # 防御性过滤：未注册进 metadata 的名字跳过（正常应全部命中）
                tables = [Base.metadata.tables[n] for n in _REBUILD_TABLES if n in Base.metadata]
                # drop_all 按 metadata 依赖序删除；SQLite 外键默认不启用（session 也未开启），
                # 无需像旧实现那样先 PRAGMA foreign_keys = OFF
                Base.metadata.drop_all(sync_conn, tables=tables, checkfirst=True)

            await conn.run_sync(_rebuild)
        await conn.run_sync(Base.metadata.create_all)
        await _reconcile_metric_indexes(conn)

    if stale:
        # 重建标记（自检页展示），备份失败不可能走到这里
        from app.db.session import session_factory
        from app.models.system import SystemSetting

        async with session_factory() as db:
            existing = await db.get(SystemSetting, REBUILD_MARKER_KEY)
            if existing is None:
                db.add(
                    SystemSetting(
                        key=REBUILD_MARKER_KEY,
                        value=f"{datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%S')}（备份 {backup_path}）",
                    )
                )
            await db.commit()
    logger.info("数据库初始化完成")
