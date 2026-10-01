"""hwmon 驱动适配：/sys/class/hwmon pwm 通道探查与读写；非 Linux 恒空。"""

from __future__ import annotations

from pathlib import Path

from app.utils.sysfs import list_dirs, read_int, read_text

HWMON_ROOT = Path("/sys/class/hwmon")


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


def find_channel(hwmon_name: str, pwm_channel: int) -> Path | None:
    """按 chip 名 + 通道号定位 pwm 文件路径。"""
    for chip_dir in list_dirs(HWMON_ROOT):
        base = HWMON_ROOT / chip_dir
        if (read_text(base / "name") or "") == hwmon_name:
            pwm = base / f"pwm{pwm_channel}"
            if pwm.exists():
                return pwm
    return None


def read_rpm(hwmon_name: str, fan_channel: int) -> int | None:
    for chip_dir in list_dirs(HWMON_ROOT):
        base = HWMON_ROOT / chip_dir
        if (read_text(base / "name") or "") == hwmon_name:
            return read_int(base / f"fan{fan_channel}_input")
    return None


def read_pwm(hwmon_name: str, pwm_channel: int) -> int | None:
    """读原始 pwm 值（0-255），通道不存在返回 None。"""
    pwm = find_channel(hwmon_name, pwm_channel)
    return read_int(pwm) if pwm else None


def write_pwm(hwmon_name: str, pwm_channel: int, pct: float) -> bool:
    """写占空比（0-100 → 0-255），并把 pwm_enable 置 1（手动）。失败返回 False。"""
    pwm = find_channel(hwmon_name, pwm_channel)
    if not pwm:
        return False
    try:
        enable = pwm.parent / f"pwm{pwm_channel}_enable"
        if enable.exists() and read_int(enable) != 1:
            enable.write_text("1")
        pwm.write_text(str(max(0, min(255, round(pct / 100 * 255)))))
        return True
    except OSError:
        return False


def restore_auto(hwmon_name: str, pwm_channel: int) -> bool:
    """交还内核：pwm_enable=2（自动温控）或 0（按驱动默认）。"""
    pwm = find_channel(hwmon_name, pwm_channel)
    if not pwm:
        return False
    try:
        enable = pwm.parent / f"pwm{pwm_channel}_enable"
        if enable.exists():
            enable.write_text("2" if read_int(enable) else "0")
        return True
    except OSError:
        return False
