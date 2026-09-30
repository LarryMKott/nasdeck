"""SPA 静态托管：FPK 打包形态下由后端直接托管前端构建产物。

仅当 NASDECK_STATIC_DIR 指向已构建的前端 dist 时启用；开发形态（vite dev server
代理到后端）不设置该变量，路由行为完全不变。history 路由的未知路径回退
index.html，api/ws 前缀除外（保持接口 404 语义）。
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException


class SPAStaticFiles(StaticFiles):
    """带 SPA 回退的静态文件：文件不存在时返回 index.html（api/ws 除外）。"""

    async def get_response(self, path: str, scope):
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
    """把前端 dist 挂到 /（须在全部路由注册之后调用，API/WS 优先匹配）。"""
    app.mount("/", SPAStaticFiles(directory=static_dir, html=True), name="spa")
