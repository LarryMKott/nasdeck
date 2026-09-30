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
