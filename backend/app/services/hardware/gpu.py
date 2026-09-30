"""GPU 采集：实时指标未接入（契约 §6.1），仅 Linux 下尝试枚举 drm 卡。"""

from __future__ import annotations

from app.services.hardware.base import BaseCollector
from app.utils.sysfs import list_dirs, read_text


class GpuCollector(BaseCollector):
    kind = "gpu"

    async def collect(self) -> dict:
        cards = []
        for card in list_dirs("/sys/class/drm"):
            if not card.startswith("card"):
                continue
            vendor = read_text(f"/sys/class/drm/{card}/device/vendor")
            if vendor:
                cards.append({"id": card, "vendor": vendor})
        return {"name": cards[0]["id"] if cards else "", "available": bool(cards), "cards": cards}
