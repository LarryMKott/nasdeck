"""sysfs 只读工具：所有读取失败返回 None，不抛异常（采集器自身降级）。"""

from __future__ import annotations

from pathlib import Path


def read_text(path: str | Path) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None


def read_int(path: str | Path) -> int | None:
    text = read_text(path)
    try:
        return int(text) if text is not None else None
    except ValueError:
        return None


def read_float(path: str | Path) -> float | None:
    text = read_text(path)
    try:
        return round(float(text) / 1000, 1) if text is not None else None  # millidegree → ℃
    except ValueError:
        return None


def list_dirs(path: str | Path) -> list[str]:
    try:
        return sorted(p.name for p in Path(path).iterdir() if p.is_dir())
    except OSError:
        return []
