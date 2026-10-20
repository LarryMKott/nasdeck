"""GPU 硬件清单采集：枚举 drm 卡落库（实时指标见 services/monitor/gpu.py）。

架构边界（#16 决策）：硬件清单是 arch 中立能力，drm 能枚举就列；
实时指标只做 amd / nvidia / intel，Mali / Panfrost / Vivante 等板载 GPU
只列清单并标 reason=arch_unsupported，不伪造利用率。
"""

from __future__ import annotations

import re

from app.services.hardware.base import BaseCollector
from app.utils.sysfs import list_dirs, read_text

# 仅匹配 cardN 主节点：card0-DP-1 等连接器目录同样以 card 开头且带 device/vendor，
# 不收紧会把每个显示输出口误计成一张卡
_CARD_RE = re.compile(r"^card\d+$")
_VENDOR_NAMES = {"0x8086": "intel", "0x10de": "nvidia", "0x1002": "amd"}
_REALTIME_VENDORS = {"intel", "nvidia", "amd"}


class GpuCollector(BaseCollector):
    kind = "gpu"

    async def collect(self) -> dict:
        cards = []
        for card in list_dirs("/sys/class/drm"):
            if not _CARD_RE.match(card):
                continue
            vendor = read_text(f"/sys/class/drm/{card}/device/vendor")
            if not vendor:
                continue
            key = vendor.strip().lower()
            vendor_name = _VENDOR_NAMES.get(key, key)
            entry = {"id": card, "vendor": vendor, "vendor_name": vendor_name}
            entry["realtime"] = vendor_name in _REALTIME_VENDORS
            if not entry["realtime"]:
                entry["reason"] = "arch_unsupported"
            cards.append(entry)
        return {"name": cards[0]["id"] if cards else "", "available": bool(cards), "cards": cards}
