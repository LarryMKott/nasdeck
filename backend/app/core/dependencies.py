"""全局依赖注入：DB 会话、X-API-Key 鉴权（未配置则不校验，契约 §1.4）。"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import PermissionDeniedError
from app.db.session import session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """请求级会话：成功 commit / 异常 rollback，由请求收尾统一处理。"""
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


DbDep = Depends(get_db)


async def require_api_key(request: Request) -> None:
    from app.core.config import settings

    if not settings.api_key:
        return
    if request.headers.get("X-API-Key") != settings.api_key:
        raise PermissionDeniedError("invalid or missing X-API-Key header")


ApiKeyDep = Depends(require_api_key)
