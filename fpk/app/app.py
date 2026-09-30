#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""nasdeck 应用入口 shim（FPK 打包形态）。

职责（真机实测约束，勿删）：
1. 飞牛应用中心经 /app/app.py 软链做第三方应用的健康检（cmd/main start 时会重建
   该软链），本文件必须存在于应用根目录；
2. 提供与 cmd/main 等价的直接启动入口：`python app.py` ≙ `python server/main.py`，
   环境变量缺省值与 cmd/main 对齐（127.0.0.1:9800），任何启动路径行为一致。
"""
import os
import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent / "server"

# 与 cmd/main 等价的缺省值；cmd/main 已导出的环境变量优先（setdefault 不覆盖）
os.environ.setdefault("NASDECK_PORT", "9800")
os.environ.setdefault("NASDECK_HOST", "127.0.0.1")
os.environ.setdefault("NASDECK_LOG_LEVEL", "INFO")
# 与 cmd/main 对齐：本 shim 只在 FPK 布局里运行，分级鉴权默认开启
os.environ.setdefault("NASDECK_TRIM_AUTH", "true")
os.environ.setdefault("NASDECK_RAW_KEEP_MINUTES", "120")
if "TRIM_PKGVAR" in os.environ:
    # sqlite URL 三斜杠是相对路径；TRIM_PKGVAR 自带前导 /，须凑满四斜杠才是绝对路径
    os.environ.setdefault("NASDECK_DB_URL", f"sqlite+aiosqlite:///{os.environ['TRIM_PKGVAR']}/nasdeck.db")

_site = SERVER_DIR / "site-packages"
if _site.is_dir():
    sys.path.insert(0, str(_site))
sys.path.insert(0, str(SERVER_DIR))
os.chdir(SERVER_DIR)

from main import app  # noqa: E402,F401  (server/main.py 的 FastAPI 实例)

if __name__ == "__main__":
    import uvicorn

    from app.core.config import settings  # noqa: E402  (这里的 app 指后端包)

    uvicorn.run("main:app", host=settings.host, port=settings.port, log_level="info")
