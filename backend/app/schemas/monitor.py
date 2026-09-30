"""监控域 DTO：实时快照 / 温度点 / 历史响应 / 总览（契约 §2.1-2.4）。"""

from __future__ import annotations

from pydantic import BaseModel


class NetIface(BaseModel):
    rx_kbps: float
    tx_kbps: float
    rx_human: str
    tx_human: str
    total_rx_mb: float
    total_tx_mb: float


class GpuRealtime(BaseModel):
    """GPU 实时分量（契约 §2.1；AMD sysfs / NVIDIA nvidia-smi，Intel 不提供实时值）。"""

    available: bool = False
    name: str = ""
    percent: float | None = None
    vram_used_mb: float | None = None
    vram_total_mb: float | None = None
    temp_c: float | None = None
    source: str = ""


class RealtimeSnapshot(BaseModel):
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
    net: dict[str, NetIface]
    disk_io: dict[str, float]
    process_count: int
    uptime_s: int


class TemperatureItem(BaseModel):
    key: str
    chip: str
    label: str | None = None
    celsius: float
    zone: str  # cpu/nvme/disk/board/other
    grade: str  # normal/warm/hot/critical


class HistoryPoint(BaseModel):
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
    points: list[HistoryPoint]
    minutes: int
    granularity: str


class DiskHealthCount(BaseModel):
    passed: int
    warning: int
    failing: int
    unknown: int


class Summary(BaseModel):
    cpu_percent: float
    mem_percent: float
    temp_max_c: float | None
    uptime_s: int
    disk_total: int
    disk_health: DiskHealthCount
    raid_degraded: int
