"""系统资源实时采集：psutil 快照 → RealtimeSnapshot 形状的 dict（契约 §2.1）。

网络与磁盘 IO 为两次采样差分：首采速率为 0 但累计量正确，1s 调度下无感知。
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

import psutil

from app.utils.unit_convert import kbps_to_human

_last_net = {"ts": 0.0, "counters": {}}
_last_disk = {"ts": 0.0, "counters": None}


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
    vm = psutil.virtual_memory()
    sm = psutil.swap_memory()
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
        "mem_used_mb": round(vm.used / 1024 / 1024, 1),
        "mem_total_mb": round(vm.total / 1024 / 1024, 1),
        "mem_percent": vm.percent,
        "swap_percent": sm.percent,
        "net": _net_ifaces(),
        "disk_io": _disk_io(),
        "process_count": len(psutil.pids()),
        "uptime_s": int(time.time() - psutil.boot_time()),
    }
