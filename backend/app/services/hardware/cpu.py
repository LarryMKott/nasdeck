"""CPU 采集：psutil 基础信息 + Linux 下 /proc/cpuinfo 补充。"""

from __future__ import annotations

import platform

import psutil

from app.services.hardware.base import BaseCollector
from app.utils.sysfs import read_text


class CpuCollector(BaseCollector):
    """CPU 硬件清单采集器（kind="cpu"）。

    数据来源：psutil 拓扑（架构、逻辑/物理核数）+ Linux 下 /proc/cpuinfo
    直读型号名（零 fork），读不到时退回 platform.processor()。
    """

    kind = "cpu"

    async def collect(self) -> dict:
        """采集 CPU 清单信息。

        Returns:
            dict: 含 name/available（恒 True）、machine（架构）、logical_cores、
                physical_cores；name 优先取 /proc/cpuinfo 的 model name，
                缺失时退回 platform.processor()，再退 "unknown"。
        """
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
