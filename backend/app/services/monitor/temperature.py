"""温度采集与分级（契约 §2.2：grade 阈值 60/75/85；Windows 无传感器返回空表）。

来源三路：
- psutil hwmon 扫描（coretemp/acpitz/nct6795 等）；
- NVMe 直读 /sys/class/hwmon：psutil 把多块 NVMe 合并成同名 chip，键/标签无法
  区分设备，直读可带 nvmeN 设备号；
- 机械盘 SMART 温度：smartctl -n standby（休眠盘不打扰，该轮无读数），60s 缓存。
"""

from __future__ import annotations

import glob
import json
import os
import platform
import shutil
import time

import psutil

from app.utils.async_cmd import run_cmd

_ZONE_HINTS = {
    "cpu": ("coretemp", "k10temp", "zenpower", "cpu_thermal", "acpitz"),
    "nvme": ("nvme",),
    "disk": ("drivetemp",),
    "board": ("acpitz", "pch", "nct"),
}

_DISK_CACHE_TTL = 60.0
# 单次扫描同时产出温度条目与各盘 SMART 健康（disk_failed 告警/summary 数据源），
# 共用同一轮 smartctl 与 60s 缓存，不增加 fork
_disk_cache: dict = {"ts": 0.0, "items": [], "health": {}}


def _zone_for(chip: str, label: str | None) -> str:
    text = f"{chip} {label or ''}".lower()
    for zone, hints in _ZONE_HINTS.items():
        if any(h in text for h in hints):
            return "board" if zone == "board" and "pch" not in text and "acpitz" not in text else zone
    return "other"


def grade_of(celsius: float) -> str:
    if celsius >= 85:
        return "critical"
    if celsius >= 75:
        return "hot"
    if celsius >= 60:
        return "warm"
    return "normal"


def _nvme_hwmon_items(root: str = "/sys/class/hwmon") -> list[dict]:
    """/sys/class/hwmon 直读 NVMe 温度，键带 nvmeN 设备号（psutil 合并同名 chip 无法区分）。"""
    items: list[dict] = []
    for hw in sorted(glob.glob(os.path.join(root, "hwmon*"))):
        try:
            with open(os.path.join(hw, "name"), encoding="ascii") as fh:
                if fh.read().strip() != "nvme":
                    continue
            # device 软链终点 .../nvme/nvme0 → 控制器号
            ctrl = os.path.basename(os.path.realpath(os.path.join(hw, "device")))
            idx = ctrl.rsplit("nvme", 1)[-1] or "?"
        except OSError:
            continue
        for input_path in sorted(glob.glob(os.path.join(hw, "temp*_input"))):
            try:
                with open(input_path, encoding="ascii") as fh:
                    celsius = round(int(fh.read().strip()) / 1000, 1)
            except (OSError, ValueError):
                continue
            label = None
            label_path = input_path[: -len("_input")] + "_label"
            if os.path.exists(label_path):
                try:
                    with open(label_path, encoding="ascii") as fh:
                        label = fh.read().strip() or None
                except OSError:
                    label = None
            label = label or "Composite"
            items.append(
                {
                    "key": f"nvme{idx}:{label}",
                    "chip": "nvme",
                    "label": f"nvme{idx} {label}",
                    "celsius": celsius,
                    "zone": "nvme",
                    "grade": grade_of(celsius),
                }
            )
    return items


async def _smart_disk_scan() -> None:
    """机械盘扫描：smartctl -n standby -H -A -j（休眠盘立即返回不打扰，该轮无读数）。

    同时记录 smart_status 健康判定（passed/failing/unknown），供 disk_failed
    告警与 /monitor/summary 磁盘健康统计使用（此前 list_disks 无 health 字段，
    该指标恒 0、summary 恒 unknown）。
    """
    now = time.monotonic()
    if now - _disk_cache["ts"] < _DISK_CACHE_TTL:
        return
    items: list[dict] = []
    health: dict[str, str] = {}
    if shutil.which("smartctl"):
        for dev in sorted(glob.glob("/dev/sd?")):
            try:
                _rc, out, _err = await run_cmd(
                    "smartctl", "-n", "standby", "-H", "-A", "-j", dev, timeout=15
                )
                data = json.loads(out)
            except Exception:  # noqa: BLE001 单盘失败/坏 JSON 不影响其余
                continue
            name = os.path.basename(dev)
            passed = (data.get("smart_status") or {}).get("passed")
            if passed is True:
                health[name] = "passed"
            elif passed is False:
                health[name] = "failing"
            current = (data.get("temperature") or {}).get("current")
            if isinstance(current, (int, float)):
                items.append(
                    {
                        "key": f"smart:{name}",
                        "chip": "smart",
                        "label": name,
                        "celsius": round(float(current), 1),
                        "zone": "disk",
                        "grade": grade_of(current),
                    }
                )
    _disk_cache.update(ts=now, items=items, health=health)


async def _smart_disk_temps() -> list[dict]:
    await _smart_disk_scan()
    return _disk_cache["items"]


async def disk_health() -> dict[str, str]:
    """设备名（sda…）→ SMART overall 健康。与盘温共用同一轮探测与缓存。"""
    if platform.system() != "Linux":
        return {}
    await _smart_disk_scan()
    return dict(_disk_cache["health"])


async def temperatures() -> list[dict]:
    if platform.system() != "Linux" or not hasattr(psutil, "sensors_temperatures"):
        return []
    result = _nvme_hwmon_items()
    for chip, entries in (psutil.sensors_temperatures() or {}).items():
        if chip == "nvme":
            continue  # 已由 hwmon 直读（带设备号），跳过 psutil 的同名合并条目
        for idx, entry in enumerate(entries):
            if entry.current is None:
                continue
            label = entry.label or None
            result.append(
                {
                    "key": f"{chip}:{label or idx}",
                    "chip": chip,
                    "label": label,
                    "celsius": round(entry.current, 1),
                    "zone": _zone_for(chip, label),
                    "grade": grade_of(entry.current),
                }
            )
    result.extend(await _smart_disk_temps())
    return result


def max_celsius(items: list[dict]) -> float | None:
    values = [t["celsius"] for t in items]
    return round(max(values), 1) if values else None
