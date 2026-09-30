"""结构化日志配置：统一格式，级别可配。"""

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
    root.setLevel(settings.log_level.upper())
    for noisy in ("uvicorn.access", "apscheduler.executors.default"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
