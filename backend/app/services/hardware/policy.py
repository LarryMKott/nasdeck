"""硬件信息获取策略决策层：启动时探测一次系统能力，产出全进程共用的采集策略。

原则（Unraid 低占用架构）：
1. 能直读 /proc、/sys 内核文件的域选 proc 策略（零 fork，读取开销近零）；
2. 内核文件不可用（非 Linux 开发机）退回 psutil（内部同为内核文件直读）；
3. 只有内核文件给不出的信息才允许外部命令（smartctl/dmidecode/nvidia-smi…），
   且命令在位与否由本层启动时判定——采集代码只查结论，不再各自实现探测。

决策结果进程内单例（create_app 启动时 decide 并记日志）；TOOLS 注册表与
EnvCheck（契约 §2.14）共用，避免两处清单漂移。
"""

from __future__ import annotations

import logging
import platform
import shutil
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# 外部工具注册表（key → (用途, 缺失时的安装包)）：策略决策与 EnvCheck 共用
TOOLS: dict[str, tuple[str, str]] = {
    "smartctl": ("硬盘 SMART 读取", "smartmontools"),
    "sensors": ("温度/风扇/电压传感", "lm-sensors"),
    "mdadm": ("软 RAID 阵列状态", "mdadm"),
    "dmidecode": ("主板/内存条信息", "dmidecode"),
    "decode-dimms": ("内存温度", "i2c-tools"),
    "ethtool": ("网卡信息与 WOL", "ethtool"),
    "lspci": ("PCI 设备识别（主板/阵列卡）", "pciutils"),
    "nvidia-smi": ("NVIDIA GPU 实时", "NVIDIA 驱动"),
}

# 内核文件探测点（proc/sys 直读策略的判定依据）
PROC_STAT = "/proc/stat"
PROC_MEMINFO = "/proc/meminfo"
SYS_CPUFREQ = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"
SYS_DRM = "/sys/class/drm"

# GPU 实时策略（vendor key → 策略）：AMD sysfs 直读；NVIDIA 依赖 nvidia-smi；
# Intel 无内核忙闲接口（Unraid 原生同样需 intel_gpu_top 插件）——恒 unavailable
GPU_STRATEGIES = {"amd": "sysfs", "nvidia": "nvidia-smi", "intel": "unavailable"}


def _readable(path: str) -> bool:
    try:
        return Path(path).exists()
    except OSError:
        return False


@dataclass
class HardwarePolicy:
    """决策结论（进程生命周期内不变）；reasons 留档判定依据，排障/自检可展示。"""

    platform: str
    cpu_util: str  # proc | psutil
    cpu_freq: str  # sysfs | psutil
    memory: str  # meminfo | psutil
    gpu_scan: bool  # /sys/class/drm 可枚举（GPU 实时与硬件清单前提）
    gpu_vendors: dict  # vendor key → sysfs | nvidia-smi | unavailable
    tools: dict = field(default_factory=dict)  # 工具名 → 在位 bool
    reasons: dict = field(default_factory=dict)  # 探测点 → 结论说明


def decide() -> HardwarePolicy:
    """探测系统能力并产出策略；只应在进程启动时调用一次（get_policy 托管单例）。"""
    system = platform.system()
    tools = {name: bool(shutil.which(name)) for name in TOOLS}
    reasons: dict[str, str] = {}

    cpu_util = "proc" if _readable(PROC_STAT) else "psutil"
    reasons["cpu_util"] = f"/proc/stat {'可读' if cpu_util == 'proc' else '缺失 → psutil'}"

    cpu_freq = "sysfs" if _readable(SYS_CPUFREQ) else "psutil"
    reasons["cpu_freq"] = f"scaling_cur_freq {'在位' if cpu_freq == 'sysfs' else '缺失 → psutil'}"

    memory = "meminfo" if _readable(PROC_MEMINFO) else "psutil"
    reasons["memory"] = f"/proc/meminfo {'可读' if memory == 'meminfo' else '缺失 → psutil'}"

    gpu_scan = _readable(SYS_DRM)
    gpu_vendors: dict[str, str] = {}
    for vendor, strategy in GPU_STRATEGIES.items():
        if strategy == "sysfs" and not gpu_scan:
            gpu_vendors[vendor] = "unavailable"
            reasons[f"gpu_{vendor}"] = "无 /sys/class/drm"
        elif strategy == "nvidia-smi" and not tools["nvidia-smi"]:
            gpu_vendors[vendor] = "unavailable"
            reasons[f"gpu_{vendor}"] = "nvidia-smi 不在位"
        else:
            gpu_vendors[vendor] = strategy
    reasons["gpu_scan"] = f"/sys/class/drm {'可枚举' if gpu_scan else '缺失'}"

    policy = HardwarePolicy(
        platform=system,
        cpu_util=cpu_util,
        cpu_freq=cpu_freq,
        memory=memory,
        gpu_scan=gpu_scan,
        gpu_vendors=gpu_vendors,
        tools=tools,
        reasons=reasons,
    )
    logger.info(
        "硬件采集策略决策：platform=%s cpu_util=%s cpu_freq=%s memory=%s gpu_scan=%s gpu=%s 外部工具=%s",
        system,
        cpu_util,
        cpu_freq,
        memory,
        gpu_scan,
        gpu_vendors,
        [name for name, ok in tools.items() if ok] or "无",
    )
    return policy


_policy: HardwarePolicy | None = None


def get_policy() -> HardwarePolicy:
    """进程级单例；首次调用即决策。测试用 set_policy 注入覆盖。"""
    global _policy
    if _policy is None:
        _policy = decide()
    return _policy


def set_policy(policy: HardwarePolicy | None) -> None:
    """注入/重置策略（测试隔离用）。"""
    global _policy
    _policy = policy
