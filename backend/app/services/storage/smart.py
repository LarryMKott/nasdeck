"""SMART 采集与健康评估：smartctl 封装（JSON 输出），缺失/失败抛 1003（契约 §2.6）。"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from app.core.exceptions import ExternalToolError
from app.utils.async_cmd import run_cmd


def _health_of(data: dict) -> str:
    """smart_status.passed 布尔直判。

    旧实现 str(True) 查大写键表（"PASSED"）恒 unknown，且「unknown 且有 NVMe
    日志就翻 passed」的兜底把 smart_status.passed=false 的故障 NVMe 判成健康。
    """
    passed = data.get("smart_status", {}).get("passed")
    if passed is True:
        return "passed"
    if passed is False:
        return "failing"
    return "unknown"


async def smart_report(device: str) -> dict:
    """device 为不带前缀设备名。standby 休眠盘只回 device/standby/health。"""
    # -n standby：休眠盘立即返回不转起（轮询本接口不打扰盘休眠）
    rc, out, err = await run_cmd("smartctl", "-j", "-n", "standby", "-a", f"/dev/{device}", timeout=30)
    try:
        data = json.loads(out)
    except ValueError:
        data = None
    if data is None:
        # 无 JSON：真失败（不支持/打开失败）。rc==2 在 -n standby 下也可能是休眠，
        # 但休眠时 smartctl 仍输出可解析的 JSON 头，走到这里即非休眠
        raise ExternalToolError(f"smartctl failed for {device}: {err.strip()[:200]}")

    # -n standby 下 rc==2 且 JSON 可解析 = 盘在休眠（未执行 SMART 查询）
    standby = rc == 2
    report = {
        "device": device,
        "model": data.get("model_name"),
        "serial": data.get("serial_number"),
        "firmware": data.get("firmware_version"),
        "health": _health_of(data),
        "temp_c": _temperature(data),
        "power_on_hours": _attr_value(data, 9),
        "power_cycles": _attr_value(data, 12),
        "nvme_percent_used": data.get("nvme_smart_health_information_log", {}).get("percent_used"),
        "nvme_media_errors": data.get("nvme_smart_health_information_log", {}).get("media_errors"),
        "attributes": _attributes(data),
        "standby": standby,
        "assessed_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
    }
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
