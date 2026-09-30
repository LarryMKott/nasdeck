"""阵列卡采集：storcli 文本采集（MegaRAID IR）+ lspci HBA 直通检测，供 /hardware/raid_card 与硬件检测页。

storcli.collect 自带 15s TTL 缓存，多消费方（硬件慢采集、存储页）共享一轮结果。
"""

from __future__ import annotations

import asyncio

from app.services.hardware.base import BaseCollector
from app.services.storage import storcli


class RaidCardCollector(BaseCollector):
    kind = "raid_card"

    async def collect(self) -> dict:
        return await self.safe_collect()

    async def safe_collect(self) -> dict:
        try:
            card = await asyncio.to_thread(storcli.collect, _run)
        except Exception as exc:  # noqa: BLE001 采集不中断调度
            card = _storcli_unavailable(exc)
        if card.get("ok"):
            return self._shape(card)
        # storcli 无 MegaRAID 可报 → lspci 检测 HBA 直通卡（如 LSI SAS2308 IT 模式）
        hba = await _detect_hba()
        if hba:
            return {
                "name": hba["model"],
                "available": True,
                "mode": "hba",
                "driver": hba.get("driver"),
                "note": storcli.HBA_NOTE,
            }
        return {
            "name": card.get("model", "未检测到"),
            "available": False,
            "mode": card.get("mode", "none"),
            "note": card.get("note", ""),
        }

    @staticmethod
    def _shape(card: dict) -> dict:
        ctrl = card.get("controller") or {}
        return {
            "name": card.get("model", ""),
            "available": bool(card.get("ok")),
            "mode": card.get("mode"),
            "note": card.get("note", ""),
            "serial": ctrl.get("serial"),
            "firmware": ctrl.get("fw_version"),
            "fw_package": ctrl.get("fw_package"),
            "bios_version": ctrl.get("bios_version"),
            "driver": ctrl.get("driver"),
            "pci": ctrl.get("pci"),
            "cachevault": ctrl.get("cachevault"),
            "cachevault_status": ctrl.get("cachevault_status"),
            "roc_temp_c": ctrl.get("roc_temp_c"),
            "controller_temp_c": ctrl.get("controller_temp_c"),
            "auto_copyback": ctrl.get("auto_copyback"),
            "jbod_count": ctrl.get("jbod_count", 0),
            "vd_count": len(card.get("virtual_drives", [])),
            "drive_count": len(card.get("drives", [])),
            "hotspare_count": len(card.get("hotspares", [])),
        }


def _storcli_unavailable(exc: Exception) -> dict:
    return {
        "ok": False,
        "mode": "none",
        "model": "未检测到",
        "note": f"storcli 不可用: {exc}",
        "controller": None,
        "drives": [],
        "virtual_drives": [],
        "hotspares": [],
    }


async def _detect_hba() -> dict | None:
    from app.services.storage.raid import _detect_hba

    return await _detect_hba()


def _run(args: list[str], timeout: float) -> str:
    """storcli.collect 的同步执行器（运行于 to_thread 工作线程，不可 await）。"""
    from app.utils.async_cmd import run_storcli_sync

    rc, out, _err = run_storcli_sync(*args, timeout=timeout)
    return out
