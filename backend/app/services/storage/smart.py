"""SMART 采集与健康评估：smartctl 封装（JSON 输出），缺失/失败抛 1003（契约 §2.6）。"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from app.core.exceptions import ExternalToolError
from app.utils.async_cmd import run_cmd

_HEALTH_MAP = {"PASSED": "passed", "OK": "passed", "WARNING": "warning", "FAILED": "failing"}


async def smart_report(device: str) -> dict:
    """device 为不带前缀设备名。standby 休眠盘只回 device/standby/health。"""
    rc, out, err = await run_cmd("smartctl", "-j", "-a", f"/dev/{device}", timeout=30)
    if rc == 2 or "Unknown" in err:
        raise ExternalToolError(f"smartctl failed for {device}: {err.strip()[:200]}")
    try:
        data = json.loads(out)
    except ValueError as exc:
        raise ExternalToolError(f"smartctl output parse failed for {device}") from exc

    standby = data.get("device", {}).get("type") == "sat" and rc == 2
    report = {
        "device": device,
        "model": data.get("model_name"),
        "serial": data.get("serial_number"),
        "firmware": data.get("firmware_version"),
        "health": _HEALTH_MAP.get(str(data.get("smart_status", {}).get("passed")), "unknown"),
        "temp_c": _temperature(data),
        "power_on_hours": _attr_value(data, 9),
        "power_cycles": _attr_value(data, 12),
        "nvme_percent_used": data.get("nvme_smart_health_information_log", {}).get("percent_used"),
        "nvme_media_errors": data.get("nvme_smart_health_information_log", {}).get("media_errors"),
        "attributes": _attributes(data),
        "standby": standby,
        "assessed_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
    }
    if report["health"] == "unknown" and data.get("nvme_smart_health_information_log"):
        report["health"] = "passed"
    if standby:
        report.update({k: None for k in ("model", "serial", "firmware", "temp_c")})
        report["attributes"] = []
    # SMART 05 增长 → warning（健康评估规则）
    if report["health"] == "passed" and _remapped(data) and _remapped(data) > 0:
        report["health"] = "warning"
    return report


def _temperature(data: dict) -> float | None:
    temp = data.get("temperature", {})
    if isinstance(temp, dict) and temp.get("current") is not None:
        return float(temp["current"])
    nvme = data.get("nvme_smart_health_information_log", {})
    if nvme.get("temperature"):
        return round(nvme["temperature"] - 273, 1)
    return None


def _attr_value(data: dict, attr_id: int) -> int | None:
    for attr in data.get("attributes", []):
        if attr.get("id") == attr_id:
            try:
                return int(attr.get("raw", {}).get("value", 0))
            except (TypeError, ValueError):
                return None
    return None


def _remapped(data: dict) -> int | None:
    value = _attr_value(data, 5)
    return value


def _attributes(data: dict) -> list[dict]:
    return [
        {
            "id": a.get("id"),
            "name": a.get("name", ""),
            "value": a.get("value"),
            "worst": a.get("worst"),
            "threshold": a.get("thresh"),
            "raw": str(a.get("raw", {}).get("string", "")),
        }
        for a in data.get("attributes", [])
    ]
