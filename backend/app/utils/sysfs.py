"""sysfs 只读工具：所有读取失败返回 None，不抛异常（采集器自身降级）。"""

from __future__ import annotations

from pathlib import Path


def read_text(path: str | Path) -> str | None:
    """读取文本文件并去首尾空白。

    Args:
        path (str | Path): sysfs 文件路径。

    Returns:
        str | None: 文件内容（strip 后）；不可读（OSError）返回 None。
    """
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None


def read_int(path: str | Path) -> int | None:
    """读取整数文件。

    Args:
        path (str | Path): sysfs 文件路径（内容应为单个整数字面量）。

    Returns:
        int | None: 整数值；不可读或非整数字面量返回 None。
    """
    text = read_text(path)
    try:
        return int(text) if text is not None else None
    except ValueError:
        return None


def read_float(path: str | Path) -> float | None:
    """读取毫摄氏度文件并换算为摄氏度（hwmon temp 输入口径）。

    Args:
        path (str | Path): sysfs 文件路径（内容为 millidegree 整数）。

    Returns:
        float | None: 摄氏度（一位小数）；不可读或非数字返回 None。
    """
    text = read_text(path)
    try:
        return round(float(text) / 1000, 1) if text is not None else None  # millidegree → ℃
    except ValueError:
        return None


def list_dirs(path: str | Path) -> list[str]:
    """列出目录下全部子目录名（排序）。

    Args:
        path (str | Path): 目录路径。

    Returns:
        list[str]: 子目录名升序列表；不可读返回空列表。
    """
    try:
        return sorted(p.name for p in Path(path).iterdir() if p.is_dir())
    except OSError:
        return []
