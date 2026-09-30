"""存储卷与挂载点：psutil 枚举（排除伪文件系统）；物理盘清单走 lsblk（非 Linux 空）。"""

from __future__ import annotations

import json

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


async def list_disks() -> list[dict]:
    """物理磁盘清单（lsblk；非 Linux / lsblk 缺失返回空列表）。

    注意：util-linux 2.38（fnOS 1.2 实测）上 `-JOb`（-O 与 -o 混用）会返回空列表，
    必须用 `-Jb -o 显式列`（真机联调踩坑，勿改回）。
    """
    try:
        rc, out, _err = await run_cmd(
            "lsblk", "-Jb", "-o", "NAME,SIZE,TYPE,ROTA,SERIAL,MODEL,TRAN", timeout=10
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
        # 只取物理盘（有 type=disk 且非 loop/rom）
        if dev.get("type") != "disk":
            continue
        name = dev.get("name", "")
        size = int(dev.get("size") or 0)
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
            }
        )
    return disks
