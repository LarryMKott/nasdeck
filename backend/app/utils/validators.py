"""安全校验工具：文件名白名单、设备名格式（契约 §3.6）。"""

from __future__ import annotations

import re

from app.core.exceptions import InvalidParamsError, NotFoundError

_FILENAME_RE = re.compile(r"^(health_[A-Za-z0-9._-]+\.html|diagnostic_[A-Za-z0-9._-]+\.zip)$")
_DEVICE_RE = re.compile(
    r"^(sd[a-z]+|hd[a-z]+|vd[a-z]+|xvd[a-z]+|nvme[0-9]+n[0-9]+(p[0-9]+)?|mmcblk[0-9]+(p[0-9]+)?)$"
)


def validate_report_filename(filename: str) -> str:
    if not _FILENAME_RE.match(filename):
        raise NotFoundError(f"report not found: {filename}")
    return filename


def validate_device_name(device: str) -> str:
    """接受 sda / nvme0n1 / /dev/sda，统一为不带前缀名。"""
    name = device.removeprefix("/dev/")
    if not _DEVICE_RE.match(name):
        raise InvalidParamsError(f"invalid device name: {device}")
    return name


def smart_health_key(device: str) -> str:
    """lsblk 盘名 → SMART 健康/温度缓存键：sda 原样；nvme0n1 剥命名空间后缀
    回控制器名 nvme0（探测按 /dev/nvme? 控制器走，键是 nvme0）。
    三个消费方（/storage/disks、/monitor/summary、disk_failed 告警）必须同口径，
    否则 NVMe 盘恒 unknown、SMART 故障不触发告警（评审 2026-10-25 P1-1）。"""
    return re.sub(r"n\d+$", "", device) if device.startswith("nvme") else device
