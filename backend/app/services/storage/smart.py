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

    Args:
        data (dict): smartctl JSON 输出。

    Returns:
        str: "passed" / "failing" / "unknown"。
    """
    passed = data.get("smart_status", {}).get("passed")
    if passed is True:
        return "passed"
    if passed is False:
        return "failing"
    return "unknown"


async def smart_report(device: str) -> dict:
    """采集单盘 SMART 报告并做健康评估。

    Args:
        device (str): 不带前缀设备名。

    Returns:
        dict: smart_report 形状（device/model/serial/firmware/health/temp_c/attributes/
            standby/assessed_at 等）；standby 休眠盘只回 device/standby/health。

    Raises:
        ExternalToolError: smartctl 失败或输出不可解析（接口层转 1003）。
    """
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
    """提取盘温（℃）。

    Args:
        data (dict): smartctl JSON 输出。

    Returns:
        float | None: SATA 取 temperature.current；NVMe 从健康日志开尔文换算；
            两形态均无返回 None。
    """
    temp = data.get("temperature", {})
    if isinstance(temp, dict) and temp.get("current") is not None:
        return float(temp["current"])
    nvme = data.get("nvme_smart_health_information_log", {})
    if nvme.get("temperature"):
        return round(nvme["temperature"] - 273, 1)
    return None


def _attr_value(data: dict, attr_id: int) -> int | None:
    """按 attribute id 取 raw 整数值。

    Args:
        data (dict): smartctl JSON 输出。
        attr_id (int): SMART 属性 id（如 9=通电时长、12=通电次数）。

    Returns:
        int | None: raw.value 整数；属性缺失或值不可解析返回 None。
    """
    for attr in data.get("attributes", []):
        if attr.get("id") == attr_id:
            try:
                return int(attr.get("raw", {}).get("value", 0))
            except (TypeError, ValueError):
                return None
    return None


def _remapped(data: dict) -> int | None:
    """取重映射扇区数（SMART 05 属性 raw 值，健康评估规则的预警依据）。

    Args:
        data (dict): smartctl JSON 输出。

    Returns:
        int | None: 05 属性 raw 值；缺失返回 None。
    """
    value = _attr_value(data, 5)
    return value


def _attributes(data: dict) -> list[dict]:
    """归一化 SMART 属性表。

    Args:
        data (dict): smartctl JSON 输出。

    Returns:
        list[dict]: 每项 {id, name, value, worst, threshold, raw}（raw 取原始串）。
    """
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
