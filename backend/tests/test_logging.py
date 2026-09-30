"""日志级别解析：显式配置优先，dev 通道缺省 DEBUG（真机排查采集链路）。"""

from __future__ import annotations

import logging

from app.core import logging as core_logging
from app.core.config import Settings


def test_resolved_log_level_matrix():
    assert Settings(app_version="dev-0.0.3", log_level="").resolved_log_level == "DEBUG"
    assert Settings(app_version="0.0.4", log_level="").resolved_log_level == "INFO"
    assert Settings(app_version="dev-0.0.3", log_level="warning").resolved_log_level == "WARNING"
    assert Settings(app_version="0.0.4", log_level="debug").resolved_log_level == "DEBUG"


def test_setup_logging_applies_level(monkeypatch):
    from app.core.config import settings as global_settings

    root = logging.getLogger()
    old_level, old_handlers = root.level, root.handlers[:]
    monkeypatch.setattr(global_settings, "log_level", "warning")
    try:
        core_logging.setup_logging()
        assert root.level == logging.WARNING
    finally:
        root.setLevel(old_level)
        root.handlers[:] = old_handlers
