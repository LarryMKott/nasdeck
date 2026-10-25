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

# settings 导出白名单：值可安全外发的键（布尔/无敏感语义）。
# SystemSetting 是自由 KV（PUT /settings/{key} 任意 key/嵌套 value 可写），嵌套 dict
# 里的凭据、URL query token 无法靠正则穷举 —— 非白名单键值整体置 <redacted>，
# key 本身保留（排障需要知道存在哪些设置）（评审 2026-10-25 P0-C）。
_SAFE_SETTING_KEYS = frozenset({"downsample_v2_migrated"})


def _settings_for_export(dump: dict, redact: bool) -> dict:
    if not redact:
        return dump
    return {k: (v if k in _SAFE_SETTING_KEYS else "<redacted>") for k, v in dump.items()}


async def generate_diagnostic(redact: bool) -> dict:
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
        # 自由 KV 的 settings：白名单外键值整体 <redacted>，白名单内再按 key 命中
        # 打码凭据值（纵深），最后整体文本脱敏（IP/路径/序列号兜底）
        masked_settings = _settings_for_export(mask_secret_values(settings_dump, redact), redact)
        zf.writestr(
            "settings.json",
            json.dumps(desensitize(json.dumps(masked_settings), redact), ensure_ascii=False, indent=2),
        )
    (REPORT_DIR / filename).write_bytes(buffer.getvalue())
    return {"filename": filename, "url": f"/api/v1/report/diagnostic/{filename}"}
