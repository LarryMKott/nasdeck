"""阵列卡采集：storcli 文本采集（MegaRAID IR）+ lspci HBA 直通检测，供 /hardware/raid_card 与硬件检测页。

storcli.collect 自带 15s TTL 缓存，多消费方（硬件慢采集、存储页）共享一轮结果。
"""

from __future__ import annotations

import asyncio

from app.services.hardware.base import BaseCollector
from app.services.storage import storcli


class RaidCardCollector(BaseCollector):
    """阵列卡硬件清单采集器（kind="raid_card"）。

    数据来源：storcli 文本采集（MegaRAID/IR，经 storcli.collect 的 15s TTL 缓存，
    运行于 to_thread 工作线程）；无 MegaRAID 可报时经 lspci 检测 HBA 直通卡。
    """

    kind = "raid_card"

    async def collect(self) -> dict:
        """采集阵列卡信息。

        Returns:
            dict: 与 safe_collect() 相同——本采集器自身已完整兜底，
                不依赖基类 safe_collect 的异常包装。
        """
        return await self.safe_collect()

    async def safe_collect(self) -> dict:
        """采集阵列卡状态：storcli 与 lspci HBA 两级探测。

        先跑 storcli.collect（15s TTL 缓存，多消费方共享一轮结果），成功则
        _shape 整理输出；storcli 失败/无 MegaRAID 可报时降级 lspci 检测 HBA
        直通卡（如 LSI SAS2308 IT 模式）；两者皆无则返回 available=False 的
        "未检测到"结果。

        Returns:
            dict: MegaRAID 命中时为 name/available/mode/note + serial/firmware/
                fw_package/bios_version/driver/pci/cachevault/温度/开关量 +
                jbod_count/vd_count/drive_count/hotspare_count 摘要；
                HBA 命中时 mode="hba" 且带 driver/note；均未命中时 available=False。
        """
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
        """把 storcli.collect 的原始结果整理为 hardware API 输出结构。

        Args:
            card: storcli.collect 返回的完整结果（含 controller 及
                virtual_drives/drives/hotspares 列表）。

        Returns:
            dict: 面向 /hardware/raid_card 与硬件检测页的扁平摘要：
                name/available/mode/note + 控制器字段（序列号/固件/温度/开关量等）
                + 各类盘计数。
        """
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
    """构造 storcli 不可用时的统一空结果（让后续 HBA 检测与返回结构无需分支）。

    Args:
        exc: storcli.collect 抛出的异常。

    Returns:
        dict: ok=False、mode="none"、model="未检测到"、note 带异常描述的空结果，
            各列表字段恒为空表。
    """
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
    """委托 storage.raid._detect_hba 做 lspci 只读 HBA 直通卡检测。

    Returns:
        dict | None: 命中时为 {"mode": "hba", "model": ..., "driver": ...}
            （driver 附带 mpt3sas 驱动版本，真机 fnOS 1.2 实测可读）；
            lspci 缺失或未检出为 None。
    """
    from app.services.storage.raid import _detect_hba

    return await _detect_hba()


def _run(args: list[str], timeout: float) -> str:
    """storcli.collect 的同步执行器（运行于 to_thread 工作线程，不可 await）。

    Args:
        args: storcli 命令参数列表。
        timeout: 单次执行超时（秒）。

    Returns:
        str: storcli 的标准输出。
    """
    from app.utils.async_cmd import run_storcli_sync

    rc, out, _err = run_storcli_sync(*args, timeout=timeout)
    return out
