"""内存采集：psutil 容量 + Linux 下 DMI 直读 SPD（需 root，失败降级）。"""

from __future__ import annotations

import platform

import psutil

from app.services.hardware.base import BaseCollector
from app.utils.sysfs import list_dirs, read_text


class MemoryCollector(BaseCollector):
    """内存硬件清单采集器（kind="memory"）。

    数据来源：psutil virtual_memory 容量 + Linux 下 /sys/devices/system/edac/mc
    直读 EDAC 控制器推断 ECC 与 DIMM（需 root，读不到即空表降级，不影响容量）。
    """

    kind = "memory"

    async def collect(self) -> dict:
        """采集内存容量与 ECC/DIMM 信息。

        Returns:
            dict: 含 name/available（恒 True）、total_mb（MiB，一位小数）、
                ecc（检出 EDAC 控制器即 True）、dimms；dimms 每项为
                {"slot": <mc 目录名>, "size_mb": <int|None>}，size 读不到为 None。
        """
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
