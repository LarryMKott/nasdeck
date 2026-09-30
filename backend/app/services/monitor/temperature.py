"""温度采集与分级（契约 §2.2：grade 阈值 60/75/85；Windows 无传感器返回空表）。"""

from __future__ import annotations

import platform

import psutil

_ZONE_HINTS = {
    "cpu": ("coretemp", "k10temp", "zenpower", "cpu_thermal", "acpitz"),
    "nvme": ("nvme",),
    "disk": ("drivetemp",),
    "board": ("acpitz", "pch", "nct"),
}


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


async def temperatures() -> list[dict]:
    if platform.system() != "Linux" or not hasattr(psutil, "sensors_temperatures"):
        return []
    result = []
    for chip, entries in (psutil.sensors_temperatures() or {}).items():
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
    return result


def max_celsius(items: list[dict]) -> float | None:
    values = [t["celsius"] for t in items]
    return round(max(values), 1) if values else None
