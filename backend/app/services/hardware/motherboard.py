"""主板采集：DMI（/sys/class/dmi/id）+ lspci 芯片组识别；非 Linux 降级不可用。"""

from __future__ import annotations

import re

from app.services.hardware.base import BaseCollector
from app.utils.async_cmd import run_cmd
from app.utils.sysfs import read_text

DMI = "/sys/class/dmi/id"


def parse_chipset(lspci_out: str | None) -> tuple[str | None, str | None]:
    """从 lspci -nn 解析（芯片组, host bridge）。

    芯片组取 ISA bridge / LPC 控制器（如 `Intel Corporation Z370 Chipset LPC/eSPI
    Controller [8086:a2c9]` → `Intel Corporation Z370 Chipset`）；Host bridge 反映
    处理器侧平台（如 `8th Gen Core ... Host Bridge/DRAM Registers [Coffee Lake S]`）。
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
    kind = "board"

    async def collect(self) -> dict:
        vendor = read_text(f"{DMI}/board_vendor")
        if not vendor:
            return {"name": "", "available": False}
        chipset = host_bridge = None
        try:
            _rc, lspci_out, _err = await run_cmd("lspci", "-nn", timeout=10)
            chipset, host_bridge = parse_chipset(lspci_out)
        except Exception:  # noqa: BLE001 lspci 缺失（Windows）不影响 DMI 部分
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
