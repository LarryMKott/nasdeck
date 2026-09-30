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
        self.message = message
        super().__init__(message)


class NotFoundError(NasdeckError):
    code, http_status = 1001, 404


class InvalidParamsError(NasdeckError):
    code, http_status = 1002, 400


class ExternalToolError(NasdeckError):
    code, http_status = 1003, 500


class PermissionDeniedError(NasdeckError):
    code, http_status = 1004, 403


class StateConflictError(NasdeckError):
    code, http_status = 1005, 409


def _envelope(code: int, message: str) -> dict:
    return {"code": code, "message": message, "data": None}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(NasdeckError)
    async def nasdeck_error_handler(_req: Request, exc: NasdeckError):
        return JSONResponse(status_code=exc.http_status, content=_envelope(exc.code, exc.message))

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_req: Request, exc: RequestValidationError):
        # 2000：请求校验失败，message 带逐字段明细
        detail = "; ".join(
            f"{'.'.join(str(x) for x in e['loc'][1:])}: {e['msg']}" for e in exc.errors()[:5]
        )
        return JSONResponse(status_code=422, content=_envelope(2000, detail or "validation failed"))

    @app.exception_handler(Exception)
    async def unhandled_handler(_req: Request, exc: Exception):
        return JSONResponse(status_code=500, content=_envelope(5000, f"internal error: {exc}"))
