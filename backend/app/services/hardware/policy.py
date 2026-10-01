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
    "intel_gpu_top": ("Intel GPU 实时利用（核显/独显）", "intel-gpu-tools"),
}

# 内核文件探测点（proc/sys 直读策略的判定依据）
PROC_STAT = "/proc/stat"
PROC_MEMINFO = "/proc/meminfo"
SYS_CPUFREQ = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"
SYS_DRM = "/sys/class/drm"

# GPU 实时策略（vendor key → 策略）：AMD sysfs 直读；NVIDIA 依赖 nvidia-smi；
# Intel 无全局忙闲 sysfs，走 intel_gpu_top -J 长驻进程（perf PMU），在位才启用
GPU_STRATEGIES = {"amd": "sysfs", "nvidia": "nvidia-smi", "intel": "intel-gpu-top"}


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
    schemes: list = field(default_factory=list)  # 逐域采集方案（自检页/启动日志展示）


def _build_schemes(
    platform_name: str,
    cpu_util: str,
    cpu_freq: str,
    memory: str,
    gpu_scan: bool,
    gpu_vendors: dict,
    tools: dict,
) -> list[dict]:
    """按决策结论汇总每个数据域在本机实际采用的采集方案（EnvCheck 展示用）。

    ok=False 表示该域在本机不可用或降级（note 带原因/补救提示）。
    """
    linux = platform_name == "Linux"

    def scheme(domain: str, label: str, primary: str, source: str, fallback: str, ok: bool, note: str = "") -> dict:
        return {
            "domain": domain,
            "label": label,
            "primary": primary if ok else "不可用",
            "source": source,
            "fallback": fallback,
            "ok": ok,
            "note": note,
        }

    out: list[dict] = [
        scheme(
            "cpu_util",
            "CPU 使用率",
            "/proc/stat 差分" if cpu_util == "proc" else "psutil",
            "/proc/stat（内核内存文件，零 fork）"
            if cpu_util == "proc"
            else "psutil（内部读 /proc/stat，非 Linux 无此文件）",
            "psutil cpu_times",
            cpu_util == "proc",
            "" if cpu_util == "proc" else "非 Linux 或 /proc/stat 不可读，自动退回 psutil",
        ),
        scheme(
            "cpu_freq",
            "CPU 频率",
            "/sys cpufreq 直读" if cpu_freq == "sysfs" else "psutil",
            "scaling_cur_freq 逐核" if cpu_freq == "sysfs" else "psutil cpu_freq",
            "psutil cpu_freq",
            cpu_freq == "sysfs",
            "" if cpu_freq == "sysfs" else "cpufreq 不可读（部分 VM/非 x86），退回 psutil",
        ),
        scheme(
            "memory",
            "内存",
            "/proc/meminfo 全字段" if memory == "meminfo" else "psutil",
            "meminfo（含 available/buffers/cached 拆分）" if memory == "meminfo" else "psutil virtual_memory",
            "psutil virtual_memory",
            memory == "meminfo",
            "" if memory == "meminfo" else "非 Linux 或 /proc/meminfo 不可读",
        ),
        scheme(
            "net",
            "网络吞吐",
            "psutil net_io_counters",
            "/proc/net/dev（psutil 内部直读），接口求和已剔除 OVS/veth/网桥",
            "—",
            True,
            "" if linux else "非 Linux 下为 psutil 跨平台实现",
        ),
        scheme(
            "disk_io",
            "磁盘 IO",
            "psutil disk_io_counters",
            "/proc/diskstats 全盘合计差分",
            "—",
            True,
            "" if linux else "非 Linux 下为 psutil 跨平台实现",
        ),
        scheme(
            "power",
            "整机功耗（RAPL）",
            "/sys/class/powercap energy_uj 差分",
            "intel-rapl package+dram 域（仅 root 可读，fnOS 应用以 root 运行）",
            "无（显示 —）",
            linux and _readable("/sys/class/powercap/intel-rapl:0/energy_uj"),
            ""
            if (linux and _readable("/sys/class/powercap/intel-rapl:0/energy_uj"))
            else "仅 Intel + Linux 且内核暴露 energy_uj（root）时可用",
        ),
        scheme(
            "temperature",
            "温度",
            "psutil sensors + NVMe hwmon 直读 + smartctl",
            "coretemp/acpitz/nct6795（psutil）；NVMe hwmon 带设备号；机械盘 smartctl -n standby",
            "无传感器时返回空表",
            linux,
            "" if linux else "非 Linux 无传感器",
        ),
        scheme(
            "fan",
            "风扇/PWM",
            "/sys/class/hwmon pwm 通道直读写",
            "nct6795/it87 等芯片 pwm[1-6]；接管需停飞牛 pwm-fancontrol；调速 5s tick",
            "扫描结果为空即页面空态",
            linux,
            "" if linux else "非 Linux 无 hwmon",
        ),
        scheme(
            "smart",
            "硬盘 SMART",
            "smartctl -j",
            "smartctl -n standby -j（JSON 输出）；自检走 smartctl -t 状态机",
            "不可用时硬盘页健康列显示未知",
            bool(tools.get("smartctl")),
            "" if tools.get("smartctl") else "smartmontools 未安装（install_callback 缺啥装啥，失败则降级）",
        ),
        scheme(
            "soft_raid",
            "软 RAID",
            "/proc/mdstat 直读",
            "成员行+blocks 行（容量 KiB→B、[U_U] 降级判断）",
            "storcli 不覆盖软阵列",
            linux and _readable("/proc/mdstat"),
            "" if linux and _readable("/proc/mdstat") else "无 /proc/mdstat（非 Linux/无 md 模块）",
        ),
        scheme(
            "hard_raid",
            "硬 RAID",
            "storcli64（随包内置）",
            "server/bin/storcli64 文本解析（MegaRAID/HBA）",
            "无卡/工具失败时 hardware_raid 置空，软 RAID 照常",
            True,
            "仅 MegaRAID/HBA 卡机器有数据，无卡机器恒空属正常",
        ),
    ]
    # GPU 实时：逐 vendor 一行
    vendor_labels = {"intel": "Intel GPU", "nvidia": "NVIDIA GPU", "amd": "AMD GPU"}
    vendor_src = {
        "intel": "intel_gpu_top -J 长驻子进程（perf PMU），Render/3D busy+频率+包功耗",
        "nvidia": "nvidia-smi 查询（利用率/显存/温度）",
        "amd": "/sys/class/drm card 设备 gpu_busy_percent 直读",
    }
    for vendor, strategy in gpu_vendors.items():
        ok = strategy != "unavailable"
        out.append(
            scheme(
                f"gpu_{vendor}",
                vendor_labels.get(vendor, vendor),
                strategy,
                vendor_src.get(vendor, strategy),
                "不可用则 GPU 磁贴保持演示值/—",
                ok and gpu_scan,
                ""
                if ok
                else {
                    "intel": "intel_gpu_top 不在位（apt install intel-gpu-tools）",
                    "nvidia": "nvidia-smi 不在位（需 NVIDIA 驱动）",
                    "amd": "无 /sys/class/drm 可枚举",
                }.get(vendor, "不可用"),
            )
        )
    return out


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
        elif strategy == "intel-gpu-top" and not tools["intel_gpu_top"]:
            gpu_vendors[vendor] = "unavailable"
            reasons[f"gpu_{vendor}"] = "intel_gpu_top 不在位（apt install intel-gpu-tools）"
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
        schemes=_build_schemes(system, cpu_util, cpu_freq, memory, gpu_scan, gpu_vendors, tools),
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
    for s in policy.schemes:
        logger.info(
            "采集方案 %-10s %-24s 数据源=%s%s",
            s["domain"],
            s["primary"],
            s["source"],
            f"（降级：{s['note']}）" if not s["ok"] and s["note"] else "",
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
