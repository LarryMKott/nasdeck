"""监控域 DTO：实时快照 / 温度点 / 历史响应 / 总览（契约 §2.1-2.4）。"""

from __future__ import annotations

from pydantic import BaseModel


class NetIface(BaseModel):
    """网卡实时速率条目。"""
    rx_kbps: float
    tx_kbps: float
    rx_human: str
    tx_human: str
    total_rx_mb: float
    total_tx_mb: float


class GpuRealtime(BaseModel):
    """GPU 实时分量（intel_gpu_top 解析）。"""
    """GPU 实时分量（契约 §2.1；AMD sysfs / NVIDIA nvidia-smi，Intel 不提供实时值）。"""

    available: bool = False
    name: str = ""
    percent: float | None = None
    vram_used_mb: float | None = None
    vram_total_mb: float | None = None
    temp_c: float | None = None
    # intel_gpu_top 扩展：频率（实测/请求 MHz）、i915 包功耗、视频/增强引擎 busy
    freq_mhz: float | None = None
    freq_max_mhz: float | None = None
    power_w: float | None = None
    video_busy: float | None = None
    enhance_busy: float | None = None
    source: str = ""


class PowerRealtime(BaseModel):
    """功耗实时分量（RAPL）。"""
    """RAPL 实时功耗分量（Intel energy_uj 差分；非 Intel/无权限时 available=false）。"""

    available: bool = False
    watts: float | None = None
    cpu_w: float | None = None
    dram_w: float | None = None


class DiskIoDevice(BaseModel):
    """单盘实时 IO 速率条目（/proc/diskstats 差分；RAID 虚拟盘等拿不到的盘缺席，前端显"—"）。"""
    read_iops: float
    write_iops: float
    read_kbps: float
    write_kbps: float
    util_pct: float


class TopProcess(BaseModel):
    """进程榜条目（仅名称 + pid + 占用，端口页同款隐私口径，不含路径/参数）。"""
    pid: int
    name: str
    # CPU 榜：平滑后 CPU% ；内存榜：null
    percent: float | None = None
    # 内存榜：驻存 MB 与占物理内存百分比；CPU 榜：null
    rss_mb: float | None = None
    mem_percent: float | None = None


class TopProcs(BaseModel):
    """进程风暴榜（花活二期 K，medium_5s 两轮均值去抖）。"""
    cpu: list[TopProcess] = []
    mem: list[TopProcess] = []


class RealtimeSnapshot(BaseModel):
    """实时快照（秒级 WS/轮询数据源，契约 §6.1）。"""
    """实时快照（秒级 WS/轮询数据源）。"""
    ts: str
    available: bool = True
    cpu_percent: float
    cpu_per_core: list[float]
    cpu_freq_mhz: float | None = None
    # 每逻辑核当前频率（取不到的核为 null）与频率上限；契约 §2.1 可选字段
    cpu_freq_per_core: list[float | None] = []
    cpu_freq_max_mhz: float | None = None
    load: list[float]
    mem_used_mb: float
    mem_total_mb: float
    mem_percent: float
    # 可用/缓冲/缓存/系统保留分量（/proc/meminfo 口径，契约 §2.1）；缺字段时为 null
    mem_available_mb: float | None = None
    mem_buffers_mb: float | None = None
    mem_cached_mb: float | None = None
    mem_reserved_mb: float | None = None
    swap_percent: float
    # GPU 实时分量（medium_5s 采样；无卡/Intel 时 available=false 或 null）
    gpu: GpuRealtime | None = None
    # RAPL 实时功耗（Intel energy_uj 差分；不可用平台 available=false）
    power: PowerRealtime | None = None
    net: dict[str, NetIface]
    disk_io: dict[str, float]
    # 每盘 IO 速率（/proc/diskstats 差分；非 Linux / 无数据时 null）
    disk_io_devices: dict[str, DiskIoDevice] | None = None
    # 进程风暴榜（medium_5s 采样；首轮采样前 null）
    top_procs: TopProcs | None = None
    process_count: int
    uptime_s: int


class CheckupItem(BaseModel):
    """体检单项（花活二期 N；score null = 缺数据，status 恒 warn 不造假）。"""
    key: str  # oracle/capacity/raid/temp/alerts/ports
    score: float | None = None
    status: str  # ok/warn/bad
    detail: str = ""


class CheckupResponse(BaseModel):
    """一键体检（纯聚合：预言/容量/阵列/温度/告警/端口六维加权）。"""
    items: list[CheckupItem]
    score: int | None = None
    grade: str | None = None  # ok/warn/bad


class TemperatureItem(BaseModel):
    """温度传感器条目（hwmon 直读 + SMART 盘温合并）。"""
    """温度传感器条目。"""
    key: str
    chip: str
    label: str | None = None
    celsius: float
    zone: str  # cpu/nvme/disk/board/other
    grade: str  # normal/warm/hot/critical


class HistoryPoint(BaseModel):
    """历史曲线数据点。"""
    ts: str
    cpu_avg: float | None = None
    cpu_max: float | None = None
    mem_avg_mb: float | None = None
    net_avg_kbps: float | None = None
    temp_max_c: float | None = None
    gpu_avg: float | None = None
    disk_read_kbps: float | None = None
    disk_write_kbps: float | None = None
    granularity: str


class HistoryResponse(BaseModel):
    """历史曲线响应（按粒度聚合，契约 §2.4）。"""
    """历史曲线响应（按粒度聚合）。"""
    points: list[HistoryPoint]
    minutes: int
    granularity: str


class DiskHealthCount(BaseModel):
    """磁盘健康计数（passed/warning/failing/unknown）。"""
    passed: int
    warning: int
    failing: int
    unknown: int


class Summary(BaseModel):
    """总览摘要（总览页头部卡片数据源）。"""
    """总览摘要（总览页头部卡片）。"""
    cpu_percent: float
    mem_percent: float
    temp_max_c: float | None
    uptime_s: int
    disk_total: int
    disk_health: DiskHealthCount
    raid_degraded: int
