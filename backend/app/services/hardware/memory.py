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
        return {
            "name": f"{platform.machine()} 内存",
            "available": True,
            "total_mb": round(vm.total / 1024 / 1024, 1),
            "ecc": _ecc_enabled(),
            "dimms": _edac_dimms(),
        }


def _ecc_enabled() -> bool:
    """EDAC sysfs 出现 mc 控制器即视为 ECC 平台（控制器层判定，与槽位枚举分离）。"""
    return bool(list_dirs("/sys/devices/system/edac/mc"))


def _edac_dimms() -> list[dict]:
    """per-DIMM 槽位枚举：edac/mc/mcN 是内存控制器，尺寸在 mcN/dimmM 下
    （此前按 mc 层枚举，slot 显示 mc0 且 size 恒 None——评审 E 域 P2-I）。
    布局随内核版本有差异，未见 dimm 子目录时返回空表（容量走 total_mb）。
    """
    dimms = []
    for mc in list_dirs("/sys/devices/system/edac/mc"):
        for dimm in list_dirs(f"/sys/devices/system/edac/mc/{mc}/dimm"):
            base = f"/sys/devices/system/edac/mc/{mc}/dimm/{dimm}"
            size = read_text(f"{base}/size")
            label = read_text(f"{base}/dimm_label") or read_text(f"{base}/label")
            if size or label:
                dimms.append(
                    {
                        "slot": f"{mc}/{dimm}",
                        "size_mb": int(size) if size and size.isdigit() else None,
                        "label": label,
                    }
                )
    return dimms
