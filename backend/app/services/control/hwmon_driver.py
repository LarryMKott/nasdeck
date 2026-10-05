"""hwmon 驱动适配：/sys/class/hwmon pwm 通道探查与读写；非 Linux 恒空。"""

from __future__ import annotations

import contextlib
from pathlib import Path

from app.utils.sysfs import list_dirs, read_int, read_text

HWMON_ROOT = Path("/sys/class/hwmon")


def scan_channels(root: Path = HWMON_ROOT) -> list[dict]:
    """枚举所有可控 pwm 通道（pwm 文件存在即可控；有对应转速计则带 fan_channel）。

    Args:
        root (Path): hwmon 根目录（默认 /sys/class/hwmon），测试可注入。

    Returns:
        list[dict]: 通道列表，每项含 chip / chip_path / pwm_channel /
            fan_channel / label / current_pwm_pct / current_rpm / pwm_enable /
            writable。
    """
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
    """按 chip 名 + 通道号定位 pwm 文件路径。

    Args:
        hwmon_name (str): hwmon chip 名（name 文件内容）。
        pwm_channel (int): pwm 通道号。

    Returns:
        Path | None: pwm 文件路径；chip 不存在或通道缺失时 None。
    """
    for chip_dir in list_dirs(HWMON_ROOT):
        base = HWMON_ROOT / chip_dir
        if (read_text(base / "name") or "") == hwmon_name:
            pwm = base / f"pwm{pwm_channel}"
            if pwm.exists():
                return pwm
    return None


def read_rpm(hwmon_name: str, fan_channel: int) -> int | None:
    """读风扇转速。

    Args:
        hwmon_name (str): hwmon chip 名。
        fan_channel (int): fan 通道号。

    Returns:
        int | None: 转速（RPM）；chip / 通道不存在或读取失败时 None。
    """
    for chip_dir in list_dirs(HWMON_ROOT):
        base = HWMON_ROOT / chip_dir
        if (read_text(base / "name") or "") == hwmon_name:
            return read_int(base / f"fan{fan_channel}_input")
    return None


def read_pwm(hwmon_name: str, pwm_channel: int) -> int | None:
    """读通道当前原始 pwm 值。

    Args:
        hwmon_name (str): hwmon chip 名。
        pwm_channel (int): pwm 通道号。

    Returns:
        int | None: 原始 pwm 值（0-255）；通道不存在时 None。
    """
    pwm = find_channel(hwmon_name, pwm_channel)
    return read_int(pwm) if pwm else None


def write_pwm(hwmon_name: str, pwm_channel: int, pct: float) -> bool:
    """写占空比并把通道切到手动模式（pwm_enable 置 1）。失败返回 False。

    先写值再切手动：若先切手动后写值失败（部分芯片锁定态拒绝写），通道会
    滞留在手动模式且占空比停在未知值。

    Args:
        hwmon_name (str): hwmon chip 名。
        pwm_channel (int): pwm 通道号。
        pct (float): 目标占空比百分比（0-100，越界自动截断到 0-255 原始值）。

    Returns:
        bool: 写入成功 True；通道不存在或写失败 False（写入中途失败会尽力
            restore_auto 兜底）。
    """
    pwm = find_channel(hwmon_name, pwm_channel)
    if not pwm:
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
            restore_auto(hwmon_name, pwm_channel)
        return False


def restore_auto(hwmon_name: str, pwm_channel: int) -> bool:
    """交还内核自动温控。

    pwm_enable=2（自动温控）或 0（按驱动默认）。

    Args:
        hwmon_name (str): hwmon chip 名。
        pwm_channel (int): pwm 通道号。

    Returns:
        bool: 成功 True；通道不存在或写失败 False。
    """
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
