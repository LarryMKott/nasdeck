"""每盘 IO 采集：/proc/diskstats 直读差分 → 每盘 IOPS / 读写速率 / 利用率。

零 fork（内核文件直读），随 system_resources.snapshot() 进 1s 档实时快照；
非 Linux / 文件缺失返回空 dict，前端按无数据显示"—"。只保留整盘行——分区行
（sda1/nvme0n1p1）与整盘行计数重复，剔除防双计；loop/ram 等内存盘不在列。
RAID 卡虚拟盘不出现在 diskstats，天然缺席由前端显"—"（花活二期 I 约定）。
"""

from __future__ import annotations

import re
import time

# 整盘设备名（分区行带分区后缀不匹配：sda1 / nvme0n1p1）
_WHOLE_DISK_RE = re.compile(r"^(sd[a-z]+|nvme\d+n\d+|vd[a-z]+|hd[a-z]+|mmcblk\d+|md\d+|dm-\d+)$")

_SECTOR_BYTES = 512

# 上轮采样（差分基准；read 失败不更新，避免瞬时缺读造出巨 dt）
_last: dict = {"ts": 0.0, "counters": None}


def _read_diskstats(path: str = "/proc/diskstats") -> dict[str, tuple[int, int, int, int, int]] | None:
    """解析 /proc/diskstats → {整盘名: (读完成数, 写完成数, 读扇区, 写扇区, 占用 ms)}。

    Args:
        path (str): diskstats 文件路径（默认 /proc/diskstats），测试可注入。

    Returns:
        dict[str, tuple[int, int, int, int, int]] | None: 设备 → 计数五元组
            （第 4/8/6/10/13 列）；非 Linux / 读取失败 / 无整盘行时 None。
    """
    try:
        counters: dict[str, tuple[int, int, int, int, int]] = {}
        with open(path, encoding="ascii") as fh:
            for line in fh:
                fields = line.split()
                # major minor name reads merged sectors_r ms_r writes merged sectors_w ms_w in_flight ms_io weighted
                if len(fields) < 14:
                    continue
                name = fields[2]
                if not _WHOLE_DISK_RE.match(name):
                    continue
                counters[name] = (
                    int(fields[3]),
                    int(fields[7]),
                    int(fields[5]),
                    int(fields[9]),
                    int(fields[12]),
                )
        return counters or None
    except (OSError, ValueError):
        return None


def snapshot(path: str = "/proc/diskstats") -> dict[str, dict[str, float]]:
    """两次采样差分 → 每盘 IO 速率（首采速率为 0，与整机 disk_io 同语义）。

    Args:
        path (str): diskstats 文件路径（默认 /proc/diskstats），测试可注入。

    Returns:
        dict[str, dict[str, float]]: 设备 → {read_iops, write_iops, read_kbps,
            write_kbps, util_pct}；util_pct 为设备忙时占比差分（0-100）。
    """
    global _last
    counters = _read_diskstats(path)
    if counters is None:
        return {}
    now = time.monotonic()
    dt = max(now - _last["ts"], 1e-6)
    prev = _last["counters"] or {}
    out: dict[str, dict[str, float]] = {}
    for name, (reads, writes, sectors_r, sectors_w, util_ms) in counters.items():
        old = prev.get(name)
        if old is None:  # 新设备 / 首采：无基准速率为 0
            out[name] = {
                "read_iops": 0.0,
                "write_iops": 0.0,
                "read_kbps": 0.0,
                "write_kbps": 0.0,
                "util_pct": 0.0,
            }
            continue
        out[name] = {
            "read_iops": round(max(reads - old[0], 0) / dt, 1),
            "write_iops": round(max(writes - old[1], 0) / dt, 1),
            "read_kbps": round(max(sectors_r - old[2], 0) * _SECTOR_BYTES / dt / 1024, 1),
            "write_kbps": round(max(sectors_w - old[3], 0) * _SECTOR_BYTES / dt / 1024, 1),
            "util_pct": round(min(max(util_ms - old[4], 0) / dt / 10.0, 100.0), 1),
        }
    _last.update(ts=now, counters=counters)
    return out
