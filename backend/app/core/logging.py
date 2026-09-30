"""结构化日志配置：统一格式，级别可配。

级别解析见 Settings.resolved_log_level：显式配置优先，dev 前缀包缺省 DEBUG
（真机排查采集链路），正式包 INFO。
"""

from __future__ import annotations

import logging
import sys

from app.core.config import settings


def setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s | %(message)s", "%Y-%m-%d %H:%M:%S")
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(settings.resolved_log_level)
    # 根 DEBUG 时第三方内部日志（aiosqlite 每条 DB 操作 / asyncio 事件循环 /
    # apscheduler 每秒调度心跳）无排障价值且刷屏，统一压到 WARNING；
    # httpx 保留 INFO（webhook/渠道请求一线可见）
    for noisy in ("uvicorn.access", "apscheduler", "aiosqlite", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
