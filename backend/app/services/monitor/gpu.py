"""GPU 实时采集（契约 §2.1 gpu 对象）：sysfs 优先零 fork，仅 NVIDIA 才调 nvidia-smi。

- AMD（vendor 0x1002）：device/gpu_busy_percent + mem_info_vram_{used,total} + hwmon 温度
  ——全部内核导出，纯文本只读（Unraid GPU Statistics 插件同款思路）
- NVIDIA（0x10de）：nvidia-smi --query-gpu 只查需要字段，5s 采样避免高频 fork
- Intel（0x8086）：无 sysfs 忙闲接口（Unraid 原生亦需 intel_gpu_top 插件），不提供实时值

无卡/读取失败 available=false，调用方按缺数据处理；采集永不抛异常。
"""

from __future__ import annotations

import time

from app.core.exceptions import ExternalToolError
from app.utils import sysfs
from app.utils.async_cmd import run_cmd

VENDOR_AMD, VENDOR_NVIDIA, VENDOR_INTEL = "0x1002", "0x10de", "0x8086"

# 5s 采样缓存：GPU 变化粒度粗，nvidia-smi 是 fork 外部进程（拒绝 1s 高频调用）
_cache: dict = {"ts": 0.0, "data": None}
# 卡枚举 60s 缓存：显卡不会频繁热插拔
_scan_cache: dict = {"ts": 0.0, "cards": None}


def _scan_cards(base: str = "/sys/class/drm") -> list[dict]:
    """枚举 drm 卡 → [{name, dev, vendor}]，只留 AMD/NVIDIA/Intel 三类已知 vendor。"""
    now = time.monotonic()
    if _scan_cache["cards"] is not None and now - _scan_cache["ts"] < 60.0:
        return _scan_cache["cards"]
    cards = []
    for name in sysfs.list_dirs(base):
        if not name.startswith("card") or not name[4:].isdigit():
            continue
        dev = f"{base}/{name}/device"
        vendor = (sysfs.read_text(f"{dev}/vendor") or "").strip()
        if vendor in (VENDOR_AMD, VENDOR_NVIDIA, VENDOR_INTEL):
            cards.append({"name": name, "dev": dev, "vendor": vendor})
    _scan_cache["cards"] = cards
    _scan_cache["ts"] = now
    return cards


def _amd_card(dev: str) -> dict:
    """AMD 卡实时分量：全 sysfs 直读（busy 为整数百分比，显存单位字节，温度毫摄氏度）。"""
    temp = None
    for hwmon in sysfs.list_dirs(f"{dev}/hwmon"):
        temp = sysfs.read_float(f"{dev}/hwmon/{hwmon}/temp1_input")
        if temp is not None:
            break
    return {
        "percent": sysfs.read_int(f"{dev}/gpu_busy_percent"),
        "vram_used_mb": _bytes_to_mb(sysfs.read_int(f"{dev}/mem_info_vram_used")),
        "vram_total_mb": _bytes_to_mb(sysfs.read_int(f"{dev}/mem_info_vram_total")),
        "temp_c": temp,
    }


def _bytes_to_mb(value: int | None) -> float | None:
    return round(value / 1048576, 1) if value is not None else None


def _parse_nvidia_smi(out: str) -> list[dict]:
    """解析 `--format=csv,noheader,nounits` 输出（每卡一行，缺值 [N/A] → None）。"""
    gpus = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 5:
            continue
        def num(text: str) -> float | None:
            try:
                return float(text)
            except ValueError:
                return None
        gpus.append(
            {
                "name": parts[0],
                "percent": num(parts[1]),
                "vram_used_mb": num(parts[2]),
                "vram_total_mb": num(parts[3]),
                "temp_c": num(parts[4]),
            }
        )
    return gpus


async def _nvidia_card() -> dict | None:
    """NVIDIA 首卡：只查需要的字段，减少输出文本量与解析开销。"""
    try:
        rc, out, _err = await run_cmd(
            "nvidia-smi",
            "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
            "--format=csv,noheader,nounits",
            timeout=10,
        )
    except ExternalToolError:
        return None  # 未装驱动/工具
    gpus = _parse_nvidia_smi(out) if rc == 0 else []
    return gpus[0] if gpus else None


async def collect() -> dict:
    """GPU 实时快照（5s 采样缓存）：{available, name, percent, vram_used_mb, vram_total_mb, temp_c, source}。"""
    now = time.monotonic()
    if _cache["data"] is not None and now - _cache["ts"] < 5.0:
        return _cache["data"]
    data = {
        "available": False,
        "name": "",
        "percent": None,
        "vram_used_mb": None,
        "vram_total_mb": None,
        "temp_c": None,
        "source": "",
    }
    for card in _scan_cards():
        if card["vendor"] == VENDOR_AMD:
            fields = _amd_card(card["dev"])
            if fields["percent"] is not None:
                data.update(fields, available=True, name=card["name"], source="sysfs")
                break
        elif card["vendor"] == VENDOR_NVIDIA:
            fields = await _nvidia_card()
            if fields:
                data.update(fields, available=True, name=fields.get("name") or card["name"], source="nvidia-smi")
                break
    _cache["data"] = data
    _cache["ts"] = now
    return data
