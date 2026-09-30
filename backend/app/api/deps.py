"""API 依赖项：DB 会话与鉴权统一从此导出。"""

from __future__ import annotations

from app.core.dependencies import (
    ApiKeyDep,
    DbDep,
    TrimAuthDep,
    get_db,
    require_api_key,
    require_trim_auth,
)

__all__ = [
    "ApiKeyDep",
    "DbDep",
    "TrimAuthDep",
    "get_db",
    "require_api_key",
    "require_trim_auth",
]
