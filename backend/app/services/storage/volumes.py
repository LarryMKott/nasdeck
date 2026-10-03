"""存储卷与挂载点：psutil 枚举（排除伪文件系统）；物理盘清单走 lsblk（非 Linux 空）。"""

from __future__ import annotations

import copy
import json
import time

import psutil

from app.utils.async_cmd import run_cmd
from app.utils.unit_convert import bytes_to_human

_PSEUDO_FS = {"squashfs", "tmpfs", "devtmpfs", "proc", "sysfs", "devfs", "overlay", "ramfs", "cgroup"}
_SYSTEM_MOUNTS = {"/boot/efi", "/run", "/dev/shm", "/run/user"}


def list_volumes() -> list[dict]:
    volumes = []
    for part in psutil.disk_partitions(all=False):
        if part.fstype.lower() in _PSEUDO_FS:
            continue
        if any(part.mountpoint.startswith(p) for p in _SYSTEM_MOUNTS):
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except OSError:
            continue
        volumes.append(
            {
                "device": part.device,
                "mount": part.mountpoint,
                "fs_type": part.fstype,
                "total_bytes": usage.total,
                "used_bytes": usage.used,
                "free_bytes": usage.free,
                "percent": round(usage.percent, 1),
                "opts": part.opts.split(",") if part.opts else [],
            }
        )
    return sorted(volumes, key=lambda v: v["mount"])


_DISKS_CACHE_TTL = 60.0
_disks_cache: dict = {"ts": 0.0, "data": None}


def _flatten_children(node: dict, out: list[dict]) -> None:
    """lsblk children 递归平铺为分区表（part/lvm/crypt 同层展示，type 字段区分）。"""
    for child in node.get("children") or []:
        mount = child.get("mountpoint")
        if isinstance(mount, list):  # 多挂载点时 lsblk JSON 为数组，取首个
            mount = mount[0] if mount else None
        raw_size = child.get("size")
        out.append(
            {
                "name": child.get("name", ""),
                "size_bytes": int(raw_size) if raw_size not in (None, "") else None,
                "fstype": child.get("fstype") or None,
                "mountpoint": mount or None,
                "type": child.get("type", ""),
            }
        )
        _flatten_children(child, out)


async def list_disks() -> list[dict]:
    """物理磁盘清单 + 分区/挂载点子树（拓扑层级边数据；非 Linux / lsblk 缺失返回空）。

    60s 进程内缓存：disks/summary/报告多端点共用一轮 fork（磁盘清单极少变化）。
    注意：util-linux 2.38（fnOS 1.2 实测）上 `-JOb`（-O 与 -o 混用）会返回空列表，
    必须用 `-Jb -o 显式列`（真机联调踩坑，勿改回）。
    """
    now = time.monotonic()
    if _disks_cache["data"] is not None and now - _disks_cache["ts"] < _DISKS_CACHE_TTL:
        return copy.deepcopy(_disks_cache["data"])  # 调用方会就地回填 alias/health，防污染缓存
    try:
        rc, out, _err = await run_cmd(
            "lsblk",
            "-Jb",
            "-o",
            "NAME,SIZE,TYPE,ROTA,SERIAL,MODEL,TRAN,FSTYPE,MOUNTPOINT",
            timeout=10,
        )
    except Exception:
        return []
    if rc != 0:
        return []
    try:
        devices = json.loads(out).get("blockdevices", [])
    except ValueError:
        return []
    disks = []
    for dev in devices:
        # 只取物理盘/直通块设备（type=disk；md 阵列 type=raidN、LVM type=lvm 不在此列）
        if dev.get("type") != "disk":
            continue
        name = dev.get("name", "")
        size = int(dev.get("size") or 0)
        partitions: list[dict] = []
        _flatten_children(dev, partitions)
        disks.append(
            {
                "device": name,
                "path": f"/dev/{name}",
                "serial": dev.get("serial"),
                "model": dev.get("model"),
                "transport": dev.get("tran"),
                "size_bytes": size,
                "size_human": bytes_to_human(size),
                "rotational": dev.get("rota", False),
                "partitions": partitions,
            }
        )
    _disks_cache.update(ts=now, data=disks)
    return copy.deepcopy(disks)


def _reset_for_test() -> None:
    _disks_cache.update(ts=0.0, data=None)
