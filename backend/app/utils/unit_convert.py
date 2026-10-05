"""单位转换工具（契约 §1.5：容量十进制可读串、速率 KB/s 一位小数）。"""

from __future__ import annotations


def bytes_to_human(num: int | float | None) -> str:
    """字节数 → 十进制（1000 进制）人读串。

    Args:
        num (int | float | None): 字节数；None 表示无数据源。

    Returns:
        str: 如 "4.0 TB"；None 输入返回 "—"（无数据占位，前端原样展示）。
    """
    if num is None:
        return "—"
    size = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if size < 1000 or unit == "PB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1000
    return f"{size:.1f} PB"


def kbps_to_human(kbps: float) -> str:
    """KB/s 速率 → 人读串（1024 进制，一位小数）。

    Args:
        kbps (float): 速率（KB/s）。

    Returns:
        str: 如 "12.3 MB/s"。
    """
    if kbps >= 1024 * 1024:
        return f"{kbps / 1024 / 1024:.1f} GB/s"
    if kbps >= 1024:
        return f"{kbps / 1024:.1f} MB/s"
    return f"{kbps:.1f} KB/s"
