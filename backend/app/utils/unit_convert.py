"""单位转换工具（契约 §1.5：容量十进制可读串、速率 KB/s 一位小数）。"""

from __future__ import annotations


def bytes_to_human(num: int | float | None) -> str:
    if num is None:
        return "—"
    size = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if size < 1000 or unit == "PB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1000
    return f"{size:.1f} PB"


def kbps_to_human(kbps: float) -> str:
    if kbps >= 1024 * 1024:
        return f"{kbps / 1024 / 1024:.1f} GB/s"
    if kbps >= 1024:
        return f"{kbps / 1024:.1f} MB/s"
    return f"{kbps:.1f} KB/s"


def seconds_to_uptime(seconds: int) -> str:
    days, rest = divmod(int(seconds), 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return f"{days} 天 {hours} 小时"
    if hours:
        return f"{hours} 小时 {minutes} 分"
    return f"{minutes} 分钟"
