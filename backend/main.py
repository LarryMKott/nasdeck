"""nasdeck 后端应用入口：装配 FastAPI、异常信封、鉴权、路由与后台调度器。"""

from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.v1 import api_router
from app.api.ws.realtime import router as ws_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.db import ingest
from app.db.init_db import init_db
from app.services.hardware.policy import get_policy
from app.tasks import downsampler
from app.tasks import scheduler as scheduler_tasks


async def envelope_middleware(request: Request, call_next):
    """成功信封包装（契约 §1.2）：JSON 响应统一为 {code,message,data,timestamp}。

    文件下载（FileResponse，非 JSON 类型）与 WS 不走信封。
    """
    response = await call_next(request)
    # 流式包装后的 Response 不保留 media_type 属性，从 content-type 头判断
    content_type = response.headers.get("content-type", "")
    if 200 <= response.status_code < 300 and content_type.startswith("application/json"):
        body = b""
        async for chunk in response.body_iterator:  # type: ignore[attr-defined]
            body += chunk
        data = json.loads(body) if body else None
        return JSONResponse(
            {"code": 0, "message": "ok", "data": data, "timestamp": int(time.time())},
            status_code=response.status_code,
            background=response.background,
        )
    return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger = logging.getLogger("nasdeck")
    logger.info(
        "nasdeck %s 启动 host=%s port=%s log_level=%s trim_auth=%s api_key=%s db=%s storcli=%s static=%s",
        settings.app_version,
        settings.host,
        settings.port,
        settings.resolved_log_level,
        settings.trim_auth,
        "set" if settings.api_key else "unset",
        settings.db_url,
        settings.storcli_cmd,
        settings.static_dir or "-",
    )
    await init_db()
    await downsampler.purge_legacy_aggregates()  # 一次性清除 v1 失真历史聚合（幂等）
    ingest.start()  # 采集落库单写者 worker（批量攒写，先于调度器就绪）
    scheduler_tasks.start()  # 模块入口：先注册 1s/5s/60s 采集与降采样任务，再启动调度器
    yield
    scheduler_tasks.shutdown(wait=False)
    await ingest.stop()


def create_app() -> FastAPI:
    setup_logging()  # 须先于任何业务日志：按 resolved_log_level 装配根 logger
    get_policy()  # 启动时决策硬件采集策略（单例结论全进程复用，决策依据进日志）
    app = FastAPI(title="nasdeck", version=settings.app_version, lifespan=lifespan)
    app.middleware("http")(envelope_middleware)
    register_exception_handlers(app)
    # 存活探针：根路径、无鉴权（契约 §3.0；同样走信封，data 为 {"status":"healthy"}）
    app.get("/health", include_in_schema=False)(lambda: {"status": "healthy"})
    app.include_router(api_router, prefix="/api/v1")
    app.include_router(ws_router)
    # FPK 打包形态：托管前端构建产物。须在全部路由之后挂载（API/WS 优先匹配）；
    # 变量未设或目录不存在时跳过，开发形态不受影响
    if settings.static_dir:
        from pathlib import Path

        from app.core.statics import mount_spa

        if Path(settings.static_dir).is_dir():
            mount_spa(app, settings.static_dir)
        else:
            logging.getLogger(__name__).warning(
                "NASDECK_STATIC_DIR=%s 不存在，跳过前端静态托管", settings.static_dir
            )
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.host, port=settings.port, log_level="info")

