"""RAPL 整机功耗采样：直读 /sys/class/powercap energy_uj 差分（零 fork，随 1s 快照）。

仅 Intel + Linux 且内核暴露 energy_uj 时可用（energy_uj 仅 root 可读，fnOS 应用
以 root 运行，权限满足；非 root/非 Intel/容器内缺失时 available=false）。
energy_uj 单调递增、越过 max_energy_range_uj 回绕，差分为负时补一个量程。
整机功耗用 package（CPU 整封包，含核显）+ dram 近似；dram 域按 name 动态定位
（不同世代 CPU 的域序号不同），找不到则 dram_w=None。
"""

from __future__ import annotations

import os
import time

_RAPL_ROOT = "/sys/class/powercap"

_last: dict = {"ts": 0.0, "package": None, "dram": None}


def _read_int(path: str) -> int | None:
    """读 sysfs 整数文件。

    Args:
        path (str): 文件路径。

    Returns:
        int | None: 整数值；不存在/不可读/非整数内容时 None。
    """
    try:
        with open(path, encoding="ascii") as fh:
            return int(fh.read().strip())
    except (OSError, ValueError):
        return None


def _find_dram_dir(pkg_dir: str) -> str | None:
    """在 package 子域里按 name 找 dram 目录。

    intel-rapl:0:0=core/:1=uncore/:2=dram 等（不同世代 CPU 的域序号不同，
    故按 name 动态定位）。

    Args:
        pkg_dir (str): package 域目录路径。

    Returns:
        str | None: dram 域目录路径；找不到或目录不可读时 None。
    """
    try:
        entries = os.listdir(pkg_dir)
    except OSError:
        return None
    for entry in entries:
        name_path = os.path.join(pkg_dir, entry, "name")
        try:
            with open(name_path, encoding="ascii") as fh:
                if fh.read().strip() == "dram":
                    return os.path.join(pkg_dir, entry)
        except OSError:
            continue
    return None


def _reset() -> None:
    """测试用：清空差分基线，下一样按首样处理。"""
    _last.update(ts=0.0, package=None, dram=None)


def rapl_power(root: str = _RAPL_ROOT, now: float | None = None, pkg: str = "intel-rapl:0") -> dict:
    """差分采样整机功耗，返回 {available, watts, cpu_w, dram_w}，单位 W。

    首样无差分基线按 0 计。pkg 参数为 package 域目录名，测试可在 Windows 上
    用无冒号名字伪造 sysfs。

    Args:
        root (str): powercap 根目录（默认 /sys/class/powercap），测试可注入。
        now (float | None): 当前时刻；None 取 time.monotonic()，测试可注入。
        pkg (str): package 域目录名。

    Returns:
        dict: available=False（energy_uj 不可读，如非 Intel/非 root/容器缺失）
            时其余字段为 None；available=True 时 watts=cpu_w+dram_w（dram 域
            缺失则不计入），各值保留 1 位小数。
    """
    pkg_dir = os.path.join(root, pkg)
    package = _read_int(os.path.join(pkg_dir, "energy_uj"))
    if package is None:
        return {"available": False, "watts": None, "cpu_w": None, "dram_w": None}

    dram_dir = _find_dram_dir(pkg_dir)
    dram = _read_int(os.path.join(dram_dir, "energy_uj")) if dram_dir else None
    pkg_range = _read_int(os.path.join(pkg_dir, "max_energy_range_uj"))
    dram_range = _read_int(os.path.join(dram_dir, "max_energy_range_uj")) if dram_dir else None

    ts = time.monotonic() if now is None else now
    dt = max(ts - _last["ts"], 1e-6)

    def _rate(cur: int | None, old: int | None, rng: int | None) -> float | None:
        """能量计数差分 → 功率 W；回绕（差分为负）时补一个量程，无基准返回 None。"""
        if cur is None or old is None:
            return None
        delta = cur - old
        if delta < 0 and rng:
            delta += rng  # 计数器回绕
        return max(delta / dt, 0.0) / 1e6  # µJ/s → W

    first = _last["package"] is None
    cpu_w = _rate(package, _last["package"], pkg_range)
    dram_w = _rate(dram, _last["dram"], dram_range)
    if first:
        # 首样无差分基线：按 0 计（同 net 首样惯例）；dram 域缺失则保持 None
        cpu_w = 0.0
        dram_w = 0.0 if dram_dir else None
    watts = None if cpu_w is None and dram_w is None else (cpu_w or 0.0) + (dram_w or 0.0)

    _last.update(ts=ts, package=package, dram=dram)
    return {
        "available": True,
        "watts": round(watts, 1) if watts is not None else None,
        "cpu_w": round(cpu_w, 1) if cpu_w is not None else None,
        "dram_w": round(dram_w, 1) if dram_w is not None else None,
    }
