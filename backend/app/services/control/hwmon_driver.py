"""hwmon 驱动适配：/sys/class/hwmon pwm 通道探查与读写；非 Linux 恒空。"""

from __future__ import annotations

import contextlib
from pathlib import Path

from app.utils.sysfs import list_dirs, read_int, read_text

HWMON_ROOT = Path("/sys/class/hwmon")


def _safe_chip_dir(chip_path: str | None) -> Path | None:
    """chip_path 必须落在 /sys/class/hwmon/hwmon* 之内（防任意路径写入：
    write_pwm 会向定位到的文件写 0-255 数值，chip_path 经 API 可配）。
    通过校验返回目录 Path，否则 None（调用方回退按名字定位）。"""
    if not chip_path:
        return None
    try:
        resolved = Path(chip_path).resolve()
        resolved.relative_to(HWMON_ROOT)
    except (ValueError, OSError):
        return None
    if resolved.parent != HWMON_ROOT or resolved.name.startswith("hwmon") is False:
        return None
    return resolved if resolved.is_dir() else None


def scan_channels(root: Path = HWMON_ROOT) -> list[dict]:
    """枚举所有可控 pwm 通道（pwm 文件存在即可控）；有对应转速计则带 fan_channel。"""
    channels = []
    for chip_dir in list_dirs(root):
        base = root / chip_dir
        chip = read_text(base / "name") or chip_dir
        for pwm_file in sorted(base.glob("pwm[0-9]*")):
            name = pwm_file.name
            idx = name.removeprefix("pwm")
            if not idx.isdigit():
                continue  # 排除 pwm*_mode/_enable 等
            fan_path = base / f"fan{idx}_input"
            fan_channel = int(idx) if fan_path.exists() else None
            channels.append(
                {
                    "chip": chip,
                    "chip_path": str(base),
                    "pwm_channel": int(idx),
                    "fan_channel": fan_channel,
                    "label": read_text(base / f"pwm{idx}_label"),
                    "current_pwm_pct": round((read_int(pwm_file) or 0) / 255 * 100, 1),
                    "current_rpm": read_int(fan_path),
                    "pwm_enable": read_int(base / f"pwm{idx}_enable"),
                    "writable": bool(pwm_file.stat().st_mode & 0o200) if pwm_file.exists() else False,
                }
            )
    return channels


def find_channel(hwmon_name: str, pwm_channel: int, chip_path: str | None = None) -> Path | None:
    """按 chip 实例 + 通道号定位 pwm 文件路径。

    chip_path 优先（同名芯片多实例消歧）；未提供/非法/已消失时回退按名字
    匹配第一个（旧数据兼容）。
    """
    base = _safe_chip_dir(chip_path)
    if base is not None:
        pwm = base / f"pwm{pwm_channel}"
        return pwm if pwm.exists() else None
    for chip_dir in list_dirs(HWMON_ROOT):
        base = HWMON_ROOT / chip_dir
        if (read_text(base / "name") or "") == hwmon_name:
            pwm = base / f"pwm{pwm_channel}"
            if pwm.exists():
                return pwm
    return None


def read_rpm(hwmon_name: str, fan_channel: int, chip_path: str | None = None) -> int | None:
    base = _safe_chip_dir(chip_path)
    if base is not None:
        return read_int(base / f"fan{fan_channel}_input")
    for chip_dir in list_dirs(HWMON_ROOT):
        b = HWMON_ROOT / chip_dir
        if (read_text(b / "name") or "") == hwmon_name:
            return read_int(b / f"fan{fan_channel}_input")
    return None


def read_pwm(hwmon_name: str, pwm_channel: int, chip_path: str | None = None) -> int | None:
    """读原始 pwm 值（0-255），通道不存在返回 None。"""
    pwm = find_channel(hwmon_name, pwm_channel, chip_path)
    return read_int(pwm) if pwm else None


def write_pwm(hwmon_name: str, pwm_channel: int, pct: float, chip_path: str | None = None) -> bool:
    """写占空比（0-100 → 0-255），并把 pwm_enable 置 1（手动）。失败返回 False。

    先写值再切手动：若先切手动后写值失败（部分芯片锁定态拒绝写），通道会
    滞留在手动模式且占空比停在未知值。
    """
    pwm = find_channel(hwmon_name, pwm_channel, chip_path)
    if not pwm:
        return False
    # 只读通道（ARM 板级 fan 驱动常见：可读转速但 pwm 不可写）直接拒绝，
    # 不进入「写入-失败-回滚」流程，避免每 tick 刷一次 OSError
    try:
        if not (pwm.stat().st_mode & 0o200):
            return False
    except OSError:
        return False
    try:
        pwm.write_text(str(max(0, min(255, round(pct / 100 * 255)))))
        enable = pwm.parent / f"pwm{pwm_channel}_enable"
        if enable.exists() and read_int(enable) != 1:
            enable.write_text("1")
        return True
    except OSError:
        # 写入中途失败：尽力交还内核自动温控，避免通道滞留在手动+未知占空比
        with contextlib.suppress(OSError):
            restore_auto(hwmon_name, pwm_channel, chip_path)
        return False


def restore_auto(hwmon_name: str, pwm_channel: int, chip_path: str | None = None) -> bool:
    """交还内核：pwm_enable=2（自动温控）或 0（按驱动默认）。"""
    pwm = find_channel(hwmon_name, pwm_channel, chip_path)
    if not pwm:
        return False
    try:
        enable = pwm.parent / f"pwm{pwm_channel}_enable"
        if enable.exists():
            enable.write_text("2" if read_int(enable) else "0")
        return True
    except OSError:
        return False
