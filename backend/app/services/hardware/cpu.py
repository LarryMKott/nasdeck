"""CPU 采集：psutil 基础信息 + Linux 下 /proc/cpuinfo 补充。"""

from __future__ import annotations

import platform

import psutil

from app.services.hardware.base import BaseCollector
from app.utils.sysfs import read_text


class CpuCollector(BaseCollector):
    kind = "cpu"

    async def collect(self) -> dict:
        info = {
            "name": "",
            "available": True,
            "machine": platform.machine(),
            "logical_cores": psutil.cpu_count(logical=True) or 0,
            "physical_cores": psutil.cpu_count(logical=False) or 0,
        }
        model = read_text("/proc/cpuinfo")
        if model:
            for line in model.splitlines():
                if line.startswith("model name"):
                    info["name"] = line.split(":", 1)[1].strip()
                    break
        if not info["name"]:
            info["name"] = platform.processor() or "unknown"
        return info
