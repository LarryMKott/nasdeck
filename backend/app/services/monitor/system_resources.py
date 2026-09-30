"""系统资源实时采集 → RealtimeSnapshot 形状的 dict（契约 §2.1）。

内存全读 /proc/meminfo（内核直接导出，零外部命令，Unraid 同口径），非 Linux 退回
psutil；CPU/网络/磁盘走 psutil。网络与磁盘 IO 为两次采样差分：首采速率为 0 但
累计量正确，1s 调度下无感知。
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

import psutil

from app.utils.unit_convert import kbps_to_human

_last_net = {"ts": 0.0, "counters": {}}
_last_disk = {"ts": 0.0, "counters": None}
# 内存 5s 采集缓存：变化粒度粗，1s 重复读无意义（告警引擎评估同为 5s tick）
_mem_cache = {"ts": 0.0, "data": None}


def _read_meminfo(path: str = "/proc/meminfo") -> dict[str, int] | None:
    """解析 /proc/meminfo 为 {字段: kB}；非 Linux / 读取失败 / 缺 MemAvailable 回 None。"""
    try:
        info: dict[str, int] = {}
        with open(path, encoding="ascii") as fh:
            for line in fh:
                key, _, rest = line.partition(":")
                value = rest.split()
                if value:
                    info[key] = int(value[0])
        if "MemTotal" not in info or "MemAvailable" not in info:
            return None
        return info
    except (OSError, ValueError):
        return None


def _mem_fields(info: dict[str, int]) -> dict:
    """kB 级 meminfo 字段 → MB 分量（契约 §2.1 口径）。

    used = MemTotal − MemAvailable（用户视角，含可回收缓存不计入）；
    系统保留 = used − (Buffers + Cached) 的正差额，负值（被缓存覆盖）回 None 不展示。
    """
    total, avail = info.get("MemTotal"), info.get("MemAvailable")
    if total is None or avail is None:
        return {}
    buffers, cached = info.get("Buffers"), info.get("Cached")
    used = total - avail
    reserved = used - (buffers or 0) - (cached or 0) if buffers is not None and cached is not None else None
    swap_total, swap_free = info.get("SwapTotal") or 0, info.get("SwapFree") or 0

    def mb(kb: int | None) -> float | None:
        return round(kb / 1024, 1) if kb is not None else None

    return {
        "total_mb": mb(total),
        "available_mb": mb(avail),
        "used_mb": mb(used),
        "buffers_mb": mb(buffers),
        "cached_mb": mb(cached),
        "reserved_mb": mb(reserved) if reserved is not None and reserved > 0 else None,
        "swap_percent": round((swap_total - swap_free) / swap_total * 100, 1) if swap_total else 0.0,
    }


def _mem_info() -> dict:
    """5s 缓存的内存分量 dict；Linux 直读 /proc/meminfo，否则退回 psutil。"""
    now = time.monotonic()
    if _mem_cache["data"] is None or now - _mem_cache["ts"] >= 5.0:
        info = _read_meminfo()
        if info is None:
            vm, sm = psutil.virtual_memory(), psutil.swap_memory()
            info = {
                "MemTotal": vm.total // 1024,
                "MemAvailable": vm.available // 1024,
                "Buffers": getattr(vm, "buffers", None),
                "Cached": getattr(vm, "cached", None),
                "SwapTotal": sm.total // 1024,
                "SwapFree": sm.free // 1024,
            }
            _mem_cache["data"] = _mem_fields(info)
            _mem_cache["data"]["swap_percent"] = round(sm.percent, 1)
        else:
            _mem_cache["data"] = _mem_fields(info)
        _mem_cache["ts"] = now
    return _mem_cache["data"]


def _diff(curr: dict, last: dict) -> dict[str, float]:
    dt = max(curr["ts"] - last["ts"], 1e-6)
    out = {}
    for key, value in curr["counters"].items():
        old = last["counters"].get(key) if last["counters"] else None
        out[key] = max((value - old) / dt, 0.0) if old is not None else 0.0
    return out


def _net_ifaces() -> dict[str, dict]:
    now = time.monotonic()
    counters = {k: (v.bytes_recv, v.bytes_sent) for k, v in psutil.net_io_counters(pernic=True).items() if k != "lo"}
    dt = max(now - _last_net["ts"], 1e-6)
    result = {}
    for name, (rx, tx) in counters.items():
        old = _last_net["counters"].get(name)
        rx_kbps = max((rx - old[0]) / dt / 1024, 0.0) if old else 0.0
        tx_kbps = max((tx - old[1]) / dt / 1024, 0.0) if old else 0.0
        result[name] = {
            "rx_kbps": round(rx_kbps, 1),
            "tx_kbps": round(tx_kbps, 1),
            "rx_human": kbps_to_human(rx_kbps),
            "tx_human": kbps_to_human(tx_kbps),
            "total_rx_mb": round(rx / 1024 / 1024, 1),
            "total_tx_mb": round(tx / 1024 / 1024, 1),
        }
    _last_net.update(ts=now, counters=counters)
    return result


def _disk_io() -> dict[str, float]:
    global _last_disk
    now = time.monotonic()
    disk = psutil.disk_io_counters()
    if disk is None:
        return {"read_kbps": 0.0, "write_kbps": 0.0}
    rates = _diff({"ts": now, "counters": {"r": disk.read_bytes, "w": disk.write_bytes}}, _last_disk)
    _last_disk = {"ts": now, "counters": {"r": disk.read_bytes, "w": disk.write_bytes}}
    return {
        "read_kbps": round(rates.get("r", 0.0) / 1024, 1),
        "write_kbps": round(rates.get("w", 0.0) / 1024, 1),
    }


def _per_core_freq() -> list[float | None]:
    """每逻辑核当前频率（MHz）；平台不给足每核条目时以 None 占位（Windows 实测仅回 1 条）。"""
    n = psutil.cpu_count(logical=True) or 0
    if not n:
        return []
    freqs = psutil.cpu_freq(percpu=True) or []
    if not freqs:
        return [None] * n
    current = [f.current if f else None for f in freqs]
    if len(current) >= n:
        return [round(v) if v else None for v in current[:n]]
    return [round(current[i]) if i < len(current) and current[i] else None for i in range(n)]


async def snapshot() -> dict:
    cpu_percent = psutil.cpu_percent(interval=None)
    per_core = psutil.cpu_percent(interval=None, percpu=True)
    freq = psutil.cpu_freq()
    freq_per_core = _per_core_freq()
    mem = _mem_info()
    try:
        load = [round(x, 2) for x in psutil.getloadavg()]
    except (AttributeError, OSError):
        load = []
    return {
        "ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "available": True,
        "cpu_percent": cpu_percent,
        "cpu_per_core": per_core,
        "cpu_freq_mhz": round(freq.current, 0) if freq else None,
        "cpu_freq_per_core": freq_per_core,
        "cpu_freq_max_mhz": round(freq.max, 0) if freq and freq.max else None,
        "load": load,
        "mem_used_mb": mem["used_mb"],
        "mem_total_mb": mem["total_mb"],
        # = used/total = (total-available)/total，用户视角占用（Unraid 同口径）
        "mem_percent": round(mem["used_mb"] / mem["total_mb"] * 100, 1) if mem["total_mb"] else 0.0,
        "mem_available_mb": mem["available_mb"],
        "mem_buffers_mb": mem["buffers_mb"],
        "mem_cached_mb": mem["cached_mb"],
        "mem_reserved_mb": mem["reserved_mb"],
        "swap_percent": mem["swap_percent"],
        "net": _net_ifaces(),
        "disk_io": _disk_io(),
        "process_count": len(psutil.pids()),
        "uptime_s": int(time.time() - psutil.boot_time()),
    }
