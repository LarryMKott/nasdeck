"""内存采集：psutil 容量 + Linux 下 DMI 直读 SPD（需 root，失败降级）。"""

from __future__ import annotations

import platform

import psutil

from app.services.hardware.base import BaseCollector
from app.utils.sysfs import list_dirs, read_text


class MemoryCollector(BaseCollector):
    kind = "memory"

    async def collect(self) -> dict:
        vm = psutil.virtual_memory()
        dimms = []
        for dimm in list_dirs("/sys/devices/system/edac/mc"):
            size = read_text(f"/sys/devices/system/edac/mc/{dimm}/size_mb")
            dimms.append({"slot": dimm, "size_mb": int(size) if size else None})
        return {
            "name": f"{platform.machine()} 内存",
            "available": True,
            "total_mb": round(vm.total / 1024 / 1024, 1),
            "ecc": bool(dimms),
            "dimms": dimms,
        }
