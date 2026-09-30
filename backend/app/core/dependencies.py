"""全局依赖注入：DB 会话、X-API-Key 鉴权（未配置则不校验）、飞牛形态分级鉴权。"""

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


# 写操作方法集合：飞牛形态下管理员才可调用（读只要求登录）
_ADMIN_METHODS = frozenset({"POST", "PUT", "DELETE", "PATCH"})


async def require_trim_auth(request: Request) -> None:
    """飞牛 CGI 反代形态的分级鉴权（NASDECK_TRIM_AUTH=true 时启用）。

    index.cgi 把飞牛注入的可信身份头原样转发（登录态已由飞牛在调 CGI 前校验）：
    - X-Trim-Userid：证明请求属于已登录的飞牛用户，全部接口必需；
    - X-Trim-Isadmin：写操作（风扇/PWM/WOL/告警/进程/设置等，均为非 GET）必需。
    头缺失一律 403，本机直连 9800 的无头请求因此被拒。
    """
    from app.core.config import settings

    if not settings.trim_auth:
        return
    if not request.headers.get("X-Trim-Userid", "").strip():
        raise PermissionDeniedError("未登录：须经飞牛 CGI 反代访问（缺失 X-Trim-Userid）")
    if request.method in _ADMIN_METHODS:
        if request.headers.get("X-Trim-Isadmin", "").strip().lower() not in ("true", "1"):
            raise PermissionDeniedError("该操作需要管理员账号（X-Trim-Isadmin）")


TrimAuthDep = Depends(require_trim_auth)
