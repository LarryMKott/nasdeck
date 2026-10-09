"""SPA 静态托管：FPK 打包形态下由后端直接托管前端构建产物。

仅当 NASDECK_STATIC_DIR 指向已构建的前端 dist 时启用；开发形态（vite dev server
代理到后端）不设置该变量，路由行为完全不变。history 路由的未知路径回退
index.html，api/ws 前缀除外（保持接口 404 语义）。

双访问模型资源基址：FPK 构建以 /__ND_PREFIX__ 为 vite base 占位符（CGI 反代与
统一网关的基址不同，单 dist 双形态），挂载时按 NASDECK_PUBLIC_PATH 一次性替换
index.html 落盘——启动期完成、零请求期开销，且对目录首页与 404 回退两条路径同时
生效。升级整体替换 dist 后占位符回归，下次启动再替换（幂等）。
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

# vite base 占位符（frontend/.env.fpk 的 VITE_PUBLIC_PATH）
_PUBLIC_PATH_PLACEHOLDER = "/__ND_PREFIX__"


class SPAStaticFiles(StaticFiles):
    """带 SPA 回退的静态文件：文件不存在时返回 index.html（api/ws 除外）。"""

    async def get_response(self, path: str, scope):
        """解析静态文件；404 且非 api/ws 前缀时回退 index.html（SPA history 路由）。

        Args:
            path (str): 请求的相对路径。
            scope: ASGI 连接 scope（透传父类）。

        Returns:
            Response: 静态文件响应或 index.html 回退。

        Raises:
            StarletteHTTPException: 404 但命中 api/ws 前缀（保持接口 404 语义），
                或非 404 的其它 HTTP 异常。
        """
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            # StaticFiles 抛的是 starlette 的 HTTPException（fastapi 版是其子类，接不住父类）；
            # path 经 os.path.normpath 在 Windows 上是反斜杠，守卫做分隔符归一
            normalized = path.replace("\\", "/")
            if exc.status_code == 404 and not normalized.startswith(("api/", "ws/")):
                return await super().get_response("index.html", scope)
            raise


def mount_spa(app: FastAPI, static_dir: str) -> None:
    """把前端 dist 挂到 /（须在全部路由注册之后调用，API/WS 优先匹配）。

    Args:
        app (FastAPI): 应用实例。
        static_dir (str): 前端构建产物目录（NASDECK_STATIC_DIR）。
    """
    _rewrite_public_path(static_dir)
    app.mount("/", SPAStaticFiles(directory=static_dir, html=True), name="spa")


def _rewrite_public_path(static_dir: str) -> None:
    """把 dist/index.html 的资源基址占位符按 NASDECK_PUBLIC_PATH 一次性替换落盘。

    CGI 形态 = 完整 cgi 反代前缀（/cgi/ThirdParty/{appname}/index.cgi），网关形态 =
    网关前缀（/app/{appname}），由 cmd/main 按访问模型导出；空值（开发/自托管直连）
    或占位符不存在（非 FPK 构建）时不做任何改动。重复启动幂等：替换后占位符消失。
    """
    from app.core.config import settings

    if not settings.public_path:
        return
    index = Path(static_dir) / "index.html"
    try:
        text = index.read_text(encoding="utf-8")
    except OSError:
        logging.getLogger(__name__).warning("index.html 不可读，资源基址占位符未替换")
        return
    if _PUBLIC_PATH_PLACEHOLDER not in text:
        return
    index.write_text(
        text.replace(_PUBLIC_PATH_PLACEHOLDER, settings.public_path.rstrip("/")),
        encoding="utf-8",
    )
    logging.getLogger(__name__).info(
        "前端资源基址占位符已替换为 %s（访问模型形态基址）", settings.public_path
    )
