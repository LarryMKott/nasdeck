"""GPU 硬件清单采集：枚举 drm 卡落库（实时指标见 services/monitor/gpu.py）。"""

from __future__ import annotations

import re

from app.services.hardware.base import BaseCollector
from app.utils.sysfs import list_dirs, read_text

# 仅匹配 cardN 主节点：card0-DP-1 等连接器目录同样以 card 开头且带 device/vendor，
# 不收紧会把每个显示输出口误计成一张卡
_CARD_RE = re.compile(r"^card\d+$")


class GpuCollector(BaseCollector):
    kind = "gpu"

    async def collect(self) -> dict:
        cards = []
        for card in list_dirs("/sys/class/drm"):
            if not _CARD_RE.match(card):
                continue
            vendor = read_text(f"/sys/class/drm/{card}/device/vendor")
            if vendor:
                cards.append({"id": card, "vendor": vendor})
        return {"name": cards[0]["id"] if cards else "", "available": bool(cards), "cards": cards}
