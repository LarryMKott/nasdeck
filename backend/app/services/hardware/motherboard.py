"""主板采集：DMI（/sys/class/dmi/id）→ 设备树兜底；lspci 芯片组识别；非 Linux 降级不可用。"""

from __future__ import annotations

import re

from app.services.hardware.base import BaseCollector
from app.services.hardware.policy import get_policy, read_board_field
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
        # DMI → 设备树兜底：无 DMI 的 ARM 板卡靠 /proc/device-tree 的 model/compatible
        fields = {name: read_board_field(name) for name in ("board_vendor", "board_name", "product_name")}
        if not any(fields.values()):
            # 两处都没有板级信息：如实不可用，不拿 CPU 型号冒充主板
            return {"name": "", "available": False, "reason": "no_dmi"}
        chipset = host_bridge = None
        # lspci 在位与否由策略决策层启动时判定；缺失（Windows/精简系统）不影响 DMI 部分
        if get_policy().tools.get("lspci"):
            try:
                _rc, lspci_out, _err = await run_cmd("lspci", "-nn", timeout=10)
                chipset, host_bridge = parse_chipset(lspci_out)
            except Exception:  # noqa: BLE001
                pass
        vendor = fields["board_vendor"][0] if fields["board_vendor"] else None
        model = fields["board_name"][0] if fields["board_name"] else None
        product = fields["product_name"][0] if fields["product_name"] else None
        sources = sorted({src for hit in fields.values() if hit for src in (hit[1],)})
        return {
            "name": " ".join(part for part in (vendor, model) if part).strip(),
            "available": True,
            "vendor": vendor,
            "model": model,
            "product_name": product,
            # 数据出处（dmi / device-tree）：前端与自检页据此标注，避免把 DT 值当 DMI 值
            "source": sources[0] if len(sources) == 1 else sources,
            "chipset": chipset,
            "host_bridge": host_bridge,
            "bios_vendor": read_text(f"{DMI}/bios_vendor"),
            "bios_version": read_text(f"{DMI}/bios_version"),
            "bios_date": read_text(f"{DMI}/bios_date"),
        }
