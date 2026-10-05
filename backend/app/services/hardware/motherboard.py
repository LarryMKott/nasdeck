"""主板采集：DMI（/sys/class/dmi/id）+ lspci 芯片组识别；非 Linux 降级不可用。"""

from __future__ import annotations

import re

from app.services.hardware.base import BaseCollector
from app.services.hardware.policy import get_policy
from app.utils.async_cmd import run_cmd
from app.utils.sysfs import read_text

DMI = "/sys/class/dmi/id"


def parse_chipset(lspci_out: str | None) -> tuple[str | None, str | None]:
    """从 lspci -nn 输出解析（芯片组, host bridge）。

    芯片组取 ISA bridge / LPC 控制器（如 `Intel Corporation Z370 Chipset LPC/eSPI
    Controller [8086:a2c9]` → `Intel Corporation Z370 Chipset`）；Host bridge 反映
    处理器侧平台（如 `8th Gen Core ... Host Bridge/DRAM Registers [Coffee Lake S]`）。

    Args:
        lspci_out: ``lspci -nn`` 的完整标准输出；None 按空输入处理。

    Returns:
        tuple[str | None, str | None]: (芯片组描述, host bridge 描述)，
            任一项未匹配到即为 None。
    """
    chipset = host = None
    for line in (lspci_out or "").splitlines():
        # lspci 行：`00:1f.0 ISA bridge [0601]: <描述> [8086:a2c9] (rev 08)`
        # 类名含空格（ISA bridge / Host bridge），用 `]: ` 分割最稳
        if "]: " not in line:
            continue
        head, _, desc_full = line.partition("]: ")
        desc = re.sub(r"\s*\[[0-9a-f]{4}:[0-9a-f]{4}\]\s*(\(rev \w+\))?\s*$", "", desc_full).strip()
        if chipset is None and (re.search(r"ISA bridge", head, re.I) or "[0601]" in head):
            chipset = re.sub(r"\s+LPC(/eSPI)?\s+Controller$", "", desc, flags=re.I) or desc
        if host is None and (re.search(r"Host bridge", head, re.I) or "[0600]" in head):
            host = desc
    return chipset, host


class MotherboardCollector(BaseCollector):
    """主板硬件清单采集器（kind="board"）。

    数据来源：DMI（/sys/class/dmi/id）直读厂商/型号/产品名/BIOS 三项 +
    lspci -nn 识别芯片组与 host bridge；非 Linux（DMI 不可读）降级为
    available=False，lspci 缺失只影响芯片组两项。
    """

    kind = "board"

    async def collect(self) -> dict:
        """采集主板与 BIOS 信息。

        Returns:
            dict: name 为 "厂商 型号"；available=False 表示 DMI 不可读（非 Linux）。
                另带 vendor/model/product_name/chipset/host_bridge 及
                bios_vendor/bios_version/bios_date，读不到的键为 None/空。
        """
        vendor = read_text(f"{DMI}/board_vendor")
        if not vendor:
            return {"name": "", "available": False}
        chipset = host_bridge = None
        # lspci 在位与否由策略决策层启动时判定；缺失（Windows/精简系统）不影响 DMI 部分
        if get_policy().tools.get("lspci"):
            try:
                _rc, lspci_out, _err = await run_cmd("lspci", "-nn", timeout=10)
                chipset, host_bridge = parse_chipset(lspci_out)
            except Exception:  # noqa: BLE001
                pass
        model = read_text(f"{DMI}/board_name")
        return {
            "name": f"{vendor} {model or ''}".strip(),
            "available": True,
            "vendor": vendor,
            "model": model,
            "product_name": read_text(f"{DMI}/product_name"),
            "chipset": chipset,
            "host_bridge": host_bridge,
            "bios_vendor": read_text(f"{DMI}/bios_vendor"),
            "bios_version": read_text(f"{DMI}/bios_version"),
            "bios_date": read_text(f"{DMI}/bios_date"),
        }
