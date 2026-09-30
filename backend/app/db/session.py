"""异步数据库会话工厂。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine = create_async_engine(settings.db_url, echo=False, future=True)
session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
