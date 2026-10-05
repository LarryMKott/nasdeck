"""全局异常与统一信封处理（契约 §1.2/§1.3：错误信封无 timestamp 字段）。"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class NasdeckError(Exception):
    """业务错误基类：code 即契约错误码，http_status 为对应 HTTP 状态。"""

    code = 1000
    http_status = 400

    def __init__(self, message: str = "business error"):
        """记录业务错误信息（message 即信封 message 字段）。

        Args:
            message (str): 人读错误信息。
        """
        self.message = message
        super().__init__(message)


class NotFoundError(NasdeckError):
    """资源不存在（契约 1001，HTTP 404）。"""

    code, http_status = 1001, 404


class InvalidParamsError(NasdeckError):
    """参数不合法（契约 1002，HTTP 400）。"""

    code, http_status = 1002, 400


class ExternalToolError(NasdeckError):
    """外部工具缺失/失败/超时（契约 1003，HTTP 500）。"""

    code, http_status = 1003, 500


class PermissionDeniedError(NasdeckError):
    """鉴权/权限不足（契约 1004，HTTP 403）。"""

    code, http_status = 1004, 403


class StateConflictError(NasdeckError):
    """状态冲突（契约 1005，HTTP 409；如同盘自检互斥）。"""

    code, http_status = 1005, 409


def _envelope(code: int, message: str) -> dict:
    """构造错误信封（契约 §1.3：无 timestamp 字段）。

    Args:
        code (int): 契约错误码。
        message (str): 人读错误信息。

    Returns:
        dict: {"code", "message", "data": None}。
    """
    return {"code": code, "message": message, "data": None}


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理：业务错误/请求校验/未捕获异常统一转错误信封。

    Args:
        app (FastAPI): 应用实例（main.py lifespan 中调用一次）。
    """

    @app.exception_handler(NasdeckError)
    async def nasdeck_error_handler(_req: Request, exc: NasdeckError):
        """业务错误 → 其 code/http_status 对应的信封。"""
        return JSONResponse(status_code=exc.http_status, content=_envelope(exc.code, exc.message))

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_req: Request, exc: RequestValidationError):
        """Pydantic 校验失败 → 信封 2000，message 带逐字段明细（取前 5 条）。"""
        # 2000：请求校验失败，message 带逐字段明细
        detail = "; ".join(
            f"{'.'.join(str(x) for x in e['loc'][1:])}: {e['msg']}" for e in exc.errors()[:5]
        )
        return JSONResponse(status_code=422, content=_envelope(2000, detail or "validation failed"))

    @app.exception_handler(Exception)
    async def unhandled_handler(_req: Request, exc: Exception):
        """未捕获异常 → 信封 5000（兜底防线，正常业务不应走到这里）。"""
        return JSONResponse(status_code=500, content=_envelope(5000, f"internal error: {exc}"))
