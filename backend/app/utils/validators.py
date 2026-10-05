"""安全校验工具：文件名白名单、设备名格式（契约 §3.6）。"""

from __future__ import annotations

import re

from app.core.exceptions import InvalidParamsError, NotFoundError

_FILENAME_RE = re.compile(r"^(health_[A-Za-z0-9._-]+\.html|diagnostic_[A-Za-z0-9._-]+\.zip)$")
_DEVICE_RE = re.compile(
    r"^(sd[a-z]+|hd[a-z]+|vd[a-z]+|xvd[a-z]+|nvme[0-9]+n[0-9]+(p[0-9]+)?|mmcblk[0-9]+(p[0-9]+)?)$"
)


def validate_report_filename(filename: str) -> str:
    """校验报告文件名在白名单内（防路径穿越下载任意文件）。

    Args:
        filename (str): 报告文件名（如 health_xxx.html / diagnostic_xxx.zip）。

    Returns:
        str: 原样返回（校验通过）。

    Raises:
        NotFoundError: 不在白名单（按"报告不存在"语义返回 1001）。
    """
    if not _FILENAME_RE.match(filename):
        raise NotFoundError(f"report not found: {filename}")
    return filename


def validate_device_name(device: str) -> str:
    """校验并归一设备名。

    Args:
        device (str): 接受 sda / nvme0n1 / /dev/sda 形态。

    Returns:
        str: 不带 /dev/ 前缀的设备名。

    Raises:
        InvalidParamsError: 不匹配已知盘名模式（含 nvme0 这类控制器名——
            控制器键场景由调用方先过本函数再自行回退）。
    """
    name = device.removeprefix("/dev/")
    if not _DEVICE_RE.match(name):
        raise InvalidParamsError(f"invalid device name: {device}")
    return name
