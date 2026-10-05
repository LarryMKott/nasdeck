"""系统资源实时采集 → RealtimeSnapshot 形状的 dict（契约 §2.1）。

各域的数据源策略由决策层启动时判定（services/hardware/policy.py）：内存全读
/proc/meminfo、CPU 走 /proc/stat 差值与 /sys cpufreq——内核文件直读零 fork，
非 Linux 退回 psutil。网络与磁盘 IO 为两次采样差分：首采速率为 0 但累计量
正确，1s 调度下无感知。
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

import psutil

from app.services.hardware.policy import get_policy
from app.services.monitor.power import rapl_power
from app.utils.sysfs import read_text
from app.utils.unit_convert import kbps_to_human

_last_net = {"ts": 0.0, "counters": {}}
_last_disk = {"ts": 0.0, "counters": None}
# 内存 5s 采集缓存：变化粒度粗，1s 重复读无意义（告警引擎评估同为 5s tick）
_mem_cache = {"ts": 0.0, "data": None}


def _read_meminfo(path: str = "/proc/meminfo") -> dict[str, int] | None:
    """解析 /proc/meminfo 为 {字段: kB}。

    Args:
        path (str): meminfo 文件路径（默认 /proc/meminfo），测试可注入。

    Returns:
        dict[str, int] | None: 字段 → kB 值；非 Linux / 读取失败 / 缺
            MemTotal 或 MemAvailable 时 None。
    """
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

    Args:
        info (dict[str, int]): _read_meminfo / psutil 兜底路径产出的 kB 级字段。

    Returns:
        dict: {total_mb, available_mb, used_mb, buffers_mb, cached_mb,
            reserved_mb, swap_percent}，字段缺失时对应分量为 None。
    """
    total, avail = info.get("MemTotal"), info.get("MemAvailable")
    if total is None or avail is None:
        return {}
    buffers, cached = info.get("Buffers"), info.get("Cached")
    used = total - avail
    reserved = used - (buffers or 0) - (cached or 0) if buffers is not None and cached is not None else None
    swap_total, swap_free = info.get("SwapTotal") or 0, info.get("SwapFree") or 0

    def mb(kb: int | None) -> float | None:
        """kB → MB（保留 1 位小数）；None 透传。"""
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
    """取内存分量 dict（5s 缓存，变化粒度粗、1s 重复读无意义）。

    策略由决策层判定（policy.memory）：meminfo 直读 /proc/meminfo；psutil 策略
    （或老内核缺 MemAvailable）走 psutil 兜底路径。

    Returns:
        dict: _mem_fields 形状的内存分量（psutil 兜底时 swap_percent 直接取
            psutil 口径）。
    """
    now = time.monotonic()
    if _mem_cache["data"] is None or now - _mem_cache["ts"] >= 5.0:
        info = _read_meminfo() if get_policy().memory == "meminfo" else None
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
    """两次采样计数差分 → 每秒速率（负差分按 0 计，无上一次基准的 key 为 0）。

    Args:
        curr (dict): 本次采样 {"ts": monotonic 时刻, "counters": {key: 累计值}}。
        last (dict): 上次采样（同结构）。

    Returns:
        dict[str, float]: key → 速率（单位/秒）。
    """
    dt = max(curr["ts"] - last["ts"], 1e-6)
    out = {}
    for key, value in curr["counters"].items():
        old = last["counters"].get(key) if last["counters"] else None
        out[key] = max((value - old) / dt, 0.0) if old is not None else 0.0
    return out


# 合成交换口前缀：容器 veth 对/docker 桥/软件网桥在物理口或网桥上已有同一份计数，
# 不剔除会双计（每容器 ×2；桥接物理口与网桥再 ×2）
_SYNTHETIC_NET_PREFIXES = ("veth", "docker", "br-", "virbr", "vport", "ovs-system")

# 桥成员名单 5s 缓存（/sys 目录扫描），1s tick 不重复扫
_bridge_members: dict = {"ts": 0.0, "set": frozenset()}


def _refresh_bridge_members() -> None:
    """刷新桥成员名单缓存（5s TTL，/sys/class/net 目录扫描，1s tick 不重复扫）。

    非 Linux / 无该路径按无桥成员处理。
    """
    import os

    now = time.monotonic()
    if now - _bridge_members["ts"] < 5.0:
        return
    members = []
    try:
        for name in os.listdir("/sys/class/net"):
            if os.path.exists(f"/sys/class/net/{name}/brport"):
                members.append(name)
    except OSError:
        pass  # 非 Linux / 无该路径：按无桥成员处理
    _bridge_members.update(ts=now, set=frozenset(members))


def _real_net_names(names: list[str]) -> list[str]:
    """筛选参与吞吐统计的真实接口。

    剔除回环/合成交换口/被桥接物理口（只计网桥本身，避免计数双计）。

    Args:
        names (list[str]): 全部网口名。

    Returns:
        list[str]: 保留的接口名（保持入参顺序）。
    """
    _refresh_bridge_members()
    name_set = set(names)
    out = []
    for name in names:
        if name == "lo" or name.startswith(_SYNTHETIC_NET_PREFIXES):
            continue
        if name.endswith("-ovs") and name[:-4] in name_set:
            continue  # OVS 内部口与物理口同名成对，计数重复
        if name in _bridge_members["set"]:
            continue
        out.append(name)
    return out


def _net_ifaces() -> dict[str, dict]:
    """采集真实网口流量（两次采样差分 → 速率 + 累计量）。

    合成交换口与被桥接物理口不参与统计（双计规避见模块级前缀注记）；
    首采速率为 0 但累计量正确。

    Returns:
        dict[str, dict]: 真实接口名 → {rx_kbps, tx_kbps, rx_human, tx_human,
            total_rx_mb, total_tx_mb}。
    """
    now = time.monotonic()
    all_names = list(psutil.net_io_counters(pernic=True).keys())
    keep = set(_real_net_names(all_names))
    counters = {
        k: (v.bytes_recv, v.bytes_sent)
        for k, v in psutil.net_io_counters(pernic=True).items()
        if k in keep
    }
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
    """整机磁盘 IO 速率（psutil 全局读写字节计数差分）。

    Returns:
        dict[str, float]: {read_kbps, write_kbps}（KB/s）；计数不可得时均为 0.0。
    """
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


def _read_proc_stat(path: str = "/proc/stat") -> list[tuple[int, int]] | None:
    """解析 /proc/stat 的 cpu 行 → [(总 jiffies, 空闲 jiffies), ...]，首项为全机合计。

    /proc 是内核内存文件，读取无磁盘 IO，1s 轮询开销可忽略（Unraid 同款做法，
    不 fork top/lscpu）。

    Args:
        path (str): proc stat 文件路径（默认 /proc/stat），测试可注入。

    Returns:
        list[tuple[int, int]] | None: 每逻辑核 + 全机合计的 (总, 空闲) jiffies；
            非 Linux / 解析异常 / 无有效行时 None。
    """
    try:
        rows = []
        with open(path, encoding="ascii") as fh:
            for line in fh:
                if not line.startswith("cpu"):
                    break
                fields = line.split()
                if len(fields) < 6:  # cpu + 8 计数字段中至少需到 iowait（第 4 列）
                    break
                vals = [int(v) for v in fields[1:9]]  # user nice system idle iowait irq softirq steal
                rows.append((sum(vals), vals[3] + vals[4]))  # idle + iowait 视为空闲
        return rows or None
    except (OSError, ValueError):
        return None


# /proc/stat 上一轮采样（差值算占用，只保存上一次值）
_cpu_stat_last = {"rows": None}


def _cpu_percent() -> tuple[float, list[float]]:
    """两次 /proc/stat 采样差值 → (全机占用%, 每核占用%)；首采为 0（与 psutil 同语义）。

    策略由决策层启动时判定（policy.cpu_util）：proc 直读或 psutil（其内部同为
    /proc/stat 差值，零外部命令）。启动后文件异常消失按无数据退 0，运行期不切换策略。

    Returns:
        tuple[float, list[float]]: (全机占用百分比, 每逻辑核占用百分比列表，
            均保留 1 位小数)；无数据时全 0。
    """
    if get_policy().cpu_util != "proc":
        return psutil.cpu_percent(interval=None), [
            round(v, 1) for v in psutil.cpu_percent(interval=None, percpu=True)
        ]
    rows = _read_proc_stat()
    if rows is None:
        prev = _cpu_stat_last["rows"]
        core_count = len(prev) - 1 if prev else 0
        return 0.0, [0.0] * max(core_count, 0)
    prev = _cpu_stat_last["rows"]
    _cpu_stat_last["rows"] = rows
    if not prev or len(prev) != len(rows):
        return 0.0, [0.0] * (len(rows) - 1)
    percents = [
        round(max(0.0, min(100.0, (1 - (idle1 - idle0) / (total1 - total0)) * 100)), 1)
        if total1 > total0
        else 0.0
        for (total1, idle1), (total0, idle0) in zip(rows, prev, strict=False)
    ]
    return percents[0], percents[1:]


def _psutil_per_core_freq(n: int) -> list[float | None]:
    """psutil 每核频率退路（Windows 实测仅回 1 条）。

    Args:
        n (int): 期望的逻辑核数。

    Returns:
        list[float | None]: 每核频率（MHz，取整）；平台不给足条目时以 None 占位。
    """
    freqs = psutil.cpu_freq(percpu=True) or []
    current = [f.current if f else None for f in freqs]
    if len(current) >= n:
        return [round(v) if v else None for v in current[:n]]
    return [round(current[i]) if i < len(current) and current[i] else None for i in range(n)]


_freq_max_mhz: int | None = None


def _per_core_freq() -> list[float | None]:
    """取每逻辑核当前频率（MHz）。

    策略由决策层判定（policy.cpu_freq）：

    sysfs 直读 /sys/devices/system/cpu/cpuX/cpufreq/scaling_cur_freq（内核实时导出，
    零 lscpu）；缺文件的核以 None 占位，运行期不切换策略；psutil 策略走退路实现。

    Returns:
        list[float | None]: 每逻辑核频率（MHz）；无法取核数时空列表。
    """
    global _freq_max_mhz
    n = psutil.cpu_count(logical=True) or 0
    if not n:
        return []
    if get_policy().cpu_freq != "sysfs":
        return _psutil_per_core_freq(n)
    freqs: list[float | None] = []
    for i in range(n):
        text = read_text(f"/sys/devices/system/cpu/cpu{i}/cpufreq/scaling_cur_freq")
        try:
            freqs.append(round(int(text) / 1000) if text else None)  # kHz → MHz
        except ValueError:
            freqs.append(None)
        if _freq_max_mhz is None:
            max_text = read_text(f"/sys/devices/system/cpu/cpu{i}/cpufreq/cpuinfo_max_freq")
            try:
                _freq_max_mhz = round(int(max_text) / 1000) if max_text else None
            except ValueError:
                _freq_max_mhz = None
    return freqs


async def snapshot() -> dict:
    """采集整机实时资源快照（契约 §2.1 RealtimeSnapshot 形状）。

    Returns:
        dict: 含 ts / available / cpu_percent / cpu_per_core / cpu_freq_mhz /
            cpu_freq_per_core / cpu_freq_max_mhz / load / mem_* 全家 /
            swap_percent / net（各真实网口分量）/ disk_io / power / process_count /
            uptime_s。
    """
    cpu_percent, per_core = _cpu_percent()
    freq_per_core = _per_core_freq()
    freq_mhz = next((v for v in freq_per_core if v), None)
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
        "cpu_freq_mhz": freq_mhz,
        "cpu_freq_per_core": freq_per_core,
        "cpu_freq_max_mhz": _freq_max_mhz,
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
        "power": rapl_power(),
        "process_count": len(psutil.pids()),
        "uptime_s": int(time.time() - psutil.boot_time()),
    }
