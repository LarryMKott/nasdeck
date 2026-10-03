"""异步数据库会话工厂。"""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine = create_async_engine(settings.db_url, echo=False, future=True)
session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@event.listens_for(engine.sync_engine, "connect")
def _sqlite_pragma(dbapi_conn, _record):
    """连接级 PRAGMA 调优，仅 sqlite 方言生效。

    全仓「不写裸 SQL」约定的唯一豁免点：PRAGMA 是 SQLite 驱动层配置，SQLAlchemy
    无对应抽象，故集中于此一处，业务/DDL 代码一律经 ORM 与检查器表达。采集写密集
    （秒级 raw 点）场景的三项调优：

    - WAL：写事务不再阻塞读、commit 开销大幅降低——真机实测默认 journal 模式下
      fast_tick 每 commit 全量 fsync，撞上 medium_tick 连续写事务即超 1s 被调度器跳秒；
    - synchronous=NORMAL：WAL 下安全（掉电最多丢最后事务，不损库）；
    - busy_timeout：偶发写竞争等锁 3s 而非立即报错。
    """
    if not settings.db_url.startswith("sqlite"):
        return
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=3000")
    cursor.close()
