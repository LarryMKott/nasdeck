"""诊断包生成：运行环境 + 设置 + 硬件快照打包 zip（可选脱敏）。"""

from __future__ import annotations

import json
import platform
import zipfile
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import psutil
from sqlalchemy import select

from app.core.config import settings
from app.db.session import session_factory
from app.models.system import SystemSetting
from app.services.report.desensitizer import desensitize, mask_secret_values

REPORT_DIR = Path(__file__).resolve().parents[3] / "data" / "reports"


async def generate_diagnostic(redact: bool) -> dict:
    """生成诊断包 zip（运行环境 info + settings dump，可选脱敏）并落盘 data/reports。

    Args:
        redact (bool): 是否脱敏（settings 先按 key 命中打码凭据值，再整体
            正则脱敏）。

    Returns:
        dict: {"filename": zip 文件名, "url": 下载路径}。
    """
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    filename = f"diagnostic_{ts}.zip"

    vm = psutil.virtual_memory()
    info = {
        "app_version": settings.app_version,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu_count": psutil.cpu_count(),
        "mem_total_mb": round(vm.total / 1024 / 1024, 1),
        "generated_at": datetime.now(UTC).isoformat(),
        "redacted": redact,
    }
    async with session_factory() as db:
        result = await db.execute(select(SystemSetting))
        settings_dump = {row.key: row.value for row in result.scalars()}

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("info.json", json.dumps(desensitize(json.dumps(info), redact), ensure_ascii=False, indent=2))
        # 自由 KV 的 settings：先按 key 命中打码凭据值（正则覆盖不了的形态），再整体脱敏
        masked_settings = mask_secret_values(settings_dump, redact)
        zf.writestr(
            "settings.json",
            json.dumps(desensitize(json.dumps(masked_settings), redact), ensure_ascii=False, indent=2),
        )
    (REPORT_DIR / filename).write_bytes(buffer.getvalue())
    return {"filename": filename, "url": f"/api/v1/report/diagnostic/{filename}"}
