"""温度采集与分级（契约 §2.2：grade 阈值 60/75/85；Windows 无传感器返回空表）。

来源三路：
- psutil hwmon 扫描（coretemp/acpitz/nct6795 等）；
- NVMe 直读 /sys/class/hwmon：psutil 把多块 NVMe 合并成同名 chip，键/标签无法
  区分设备，直读可带 nvmeN 设备号；
- SATA 盘 / NVMe SMART 温度与健康：smartctl -n standby（休眠盘不打扰，该轮无读数），60s 缓存。
"""

from __future__ import annotations

import asyncio
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
_disk_cache: dict = {"ts": 0.0, "items": [], "health": {}, "temps": {}}


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
    """SATA 机械盘 + NVMe 扫描：smartctl -n standby -H -A -j（休眠盘立即返回不打扰，该轮无读数）。

    同时记录 smart_status 健康判定（passed/failing/unknown），供 disk_failed
    告警、/monitor/summary 磁盘健康统计与 /storage/disks 健康回填使用。
    NVMe 按控制器（/dev/nvme?）探测，消费方把 nvme0n1 形态的 lsblk 盘名回退
    到控制器名匹配（单命名空间 NAS 场景一一对应，多命名空间共享控制器健康）。
    逐盘并发执行：medium tick 等这轮结果做风扇调速与告警评估，串行时单盘
    卡 15s × N 盘会把 5s tick 拖到分钟级（scheduler max_instances=1 顺延）。
    """
    now = time.monotonic()
    if now - _disk_cache["ts"] < _DISK_CACHE_TTL:
        return
    items: list[dict] = []
    health: dict[str, str] = {}
    temps: dict[str, float] = {}
    if shutil.which("smartctl"):
        devices = sorted(glob.glob("/dev/sd?")) + sorted(glob.glob("/dev/nvme?"))
        results = await asyncio.gather(
            *(_probe_disk(dev) for dev in devices), return_exceptions=True
        )
        for _dev, result in zip(devices, results, strict=False):
            if isinstance(result, Exception):
                continue  # 单盘失败不影响其余
            name, data = result
            if data is None:
                continue
            passed = (data.get("smart_status") or {}).get("passed")
            if passed is True:
                health[name] = "passed"
            elif passed is False:
                health[name] = "failing"
            current = (data.get("temperature") or {}).get("current")
            if isinstance(current, (int, float)):
                temps[name] = round(float(current), 1)
                if name.startswith("nvme"):
                    continue  # NVMe 温度已由 hwmon 直读条目上屏（zone nvme），不重复列
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
    _disk_cache.update(ts=now, items=items, health=health, temps=temps)


async def _probe_disk(dev: str) -> tuple[str, dict | None]:
    """单盘探测：返回 (设备名, JSON dict)；无 JSON 输出返回 (设备名, None)。"""
    try:
        _rc, out, _err = await run_cmd(
            "smartctl", "-n", "standby", "-H", "-A", "-j", dev, timeout=15
        )
        return os.path.basename(dev), json.loads(out)
    except Exception:  # noqa: BLE001 超时/缺工具/坏 JSON 都按该盘无数据
        return os.path.basename(dev), None


async def _smart_disk_temps() -> list[dict]:
    await _smart_disk_scan()
    return _disk_cache["items"]


async def disk_health() -> dict[str, str]:
    """设备名（sda / nvme0）→ SMART overall 健康。与盘温共用同一轮探测与缓存。"""
    if platform.system() != "Linux":
        return {}
    await _smart_disk_scan()
    return dict(_disk_cache["health"])


async def disk_temps() -> dict[str, float]:
    """设备名（sda / nvme0）→ SMART 温度 ℃。休眠盘该轮无读数，不在返回值中。"""
    if platform.system() != "Linux":
        return {}
    await _smart_disk_scan()
    return dict(_disk_cache["temps"])


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
