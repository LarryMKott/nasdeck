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
    """校验 X-API-Key 头（未配置 api_key 时放行，直连无鉴权形态）。

    Args:
        request (Request): 当前请求（读头）。

    Raises:
        PermissionDeniedError: 配置了 api_key 且头缺失/不匹配。
    """
    from app.core.config import settings

    if not settings.api_key:
        return
    if request.headers.get("X-API-Key") != settings.api_key:
        raise PermissionDeniedError("invalid or missing X-API-Key header")


ApiKeyDep = Depends(require_api_key)


# 写操作方法集合：飞牛形态下管理员才可调用（读只要求登录）
_ADMIN_METHODS = frozenset({"POST", "PUT", "DELETE", "PATCH"})


async def require_trim_auth(request: Request) -> None:
    """飞牛形态的分级鉴权（NASDECK_TRIM_AUTH=true 时启用）。

    两种入口形态的信任链：
    - CGI 反代（NASDECK_UDS 空）：index.cgi 把飞牛注入的可信身份头原样转发（登录态
      已由飞牛在调 CGI 前校验），并附代理共享密钥——
      · X-Nasdeck-Proxy：本机代理共享密钥（NASDECK_PROXY_TOKEN），证明身份头来自
        持密的 index.cgi 而非客户端/任意本机进程伪造（网关是否剥离客户端同名
        X-Trim-* 头无法保证，此为根防线）；
      · X-Trim-Userid：证明请求属于已登录的飞牛用户，全部接口必需；
      · X-Trim-Isadmin：写操作（风扇/PWM/WOL/告警/进程/设置等，均为非 GET）必需。
    - 统一网关（NASDECK_UDS 非空）：trim_http_cgi 校验登录态后经 Unix Socket 转发，
      无 index.cgi 参与故无代理密钥——socket 文件权限即信任边界（等价强度），
      跳过 X-Nasdeck-Proxy 校验；X-Trim-Userid / Isadmin 语义不变（网关转发）。
    头缺失一律 403，本机直连的无头请求因此被拒。
    """
    import hmac

    from app.core.config import settings

    if not settings.trim_auth:
        return
    if settings.proxy_token and not settings.uds and not hmac.compare_digest(
        request.headers.get("X-Nasdeck-Proxy", ""), settings.proxy_token
    ):
        raise PermissionDeniedError("缺少代理信任凭据（X-Nasdeck-Proxy）")
    if not request.headers.get("X-Trim-Userid", "").strip():
        raise PermissionDeniedError("未登录：须经飞牛 CGI 反代访问（缺失 X-Trim-Userid）")
    if request.method in _ADMIN_METHODS:
        if request.headers.get("X-Trim-Isadmin", "").strip().lower() not in ("true", "1"):
            raise PermissionDeniedError("该操作需要管理员账号（X-Trim-Isadmin）")


TrimAuthDep = Depends(require_trim_auth)
