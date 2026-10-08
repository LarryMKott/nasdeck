"""存储域 DTO：磁盘 / SMART / 自检 / 阵列 / 卷（契约 §2.5-2.9）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PartitionItem(BaseModel):
    """分区/子拓扑条目（lsblk children 平铺）。"""
    name: str  # 不带 /dev/ 前缀（sda1 / dm-0）
    size_bytes: int | None = None
    fstype: str | None = None
    mountpoint: str | None = None
    type: str = "part"  # part/lvm/crypt…（lsblk TYPE，非分区形态平铺展示）


class OracleDim(BaseModel):
    """健康雷达维度（花活二期 J）：0-100 子分，null = 无数据。"""
    key: str  # reallocated/pending/media/temp/wear
    value: float | None = None


class OracleEta(BaseModel):
    """触阈值倒计时（拿得到 THRESH 且有正增速才给出）。"""
    metric: str
    days: float
    current: float
    threshold: float
    slope_per_day: float


class DiskOracle(BaseModel):
    """硬盘健康预言：0-100 健康分 + 五维雷达 + 触阈值 ETA（smart_points 1h 桶斜率）。"""
    score: int | None = None  # null = 连当前值都拿不到（盘未采样）
    grade: str | None = None  # good(≥85)/watch(≥60)/bad(<60)
    has_history: bool = False  # 窗口内有无 1h 桶历史（新盘只按当前值给分）
    dims: list[OracleDim] = []
    etas: list[OracleEta] = []


class DiskItem(BaseModel):
    """物理磁盘（合并别名/SMART 健康/温度，契约 §2.5）。"""
    device: str  # 不带 /dev/ 前缀
    path: str
    serial: str | None = None
    model: str | None = None
    transport: str | None = None
    size_bytes: int
    size_human: str
    rotational: bool
    alias: str | None = None
    health: str = "unknown"  # passed/failing/unknown（SMART 慢采集缓存回填）
    temp_c: float | None = None
    power_on_hours: int | None = None
    oracle: DiskOracle | None = None  # 健康预言（花活二期 J；盘未采样时 null）
    partitions: list[PartitionItem] = []  # lsblk children 平铺（拓扑树层级边）


class SmartAttribute(BaseModel):
    """SMART 属性行（ATA 属性表单行）。"""
    id: int
    name: str
    value: int | None
    worst: int | None
    threshold: int | None
    raw: str | None


class SmartReport(BaseModel):
    """SMART 报告（契约 §2.6；休眠盘仅 device/standby/health）。"""
    device: str
    model: str | None = None
    serial: str | None = None
    firmware: str | None = None
    health: str = "unknown"
    temp_c: float | None = None
    power_on_hours: int | None = None
    power_cycles: int | None = None
    nvme_percent_used: int | None = None
    nvme_media_errors: int | None = None
    attributes: list[SmartAttribute] = []
    standby: bool = False
    assessed_at: str | None = None


class AliasIn(BaseModel):
    """磁盘别名写入请求体。"""
    alias: str = Field(min_length=1, max_length=64)


class AliasOut(BaseModel):
    """别名响应。"""
    serial: str
    alias: str | None = None


class AliasDeleted(BaseModel):
    """别名删除响应。"""
    serial: str
    deleted: bool


class RaidMemberItem(BaseModel):
    """阵列成员盘（storcli PD / mdadm 成员两形态，字段可空）。"""
    slot: str | None = None  # storcli 槽位 "E:S"；mdadm 无此字段
    sn: str | None = None
    model: str | None = None
    state: str | None = None
    media: str | None = None  # HDD/SSD（storcli）
    size_human: str | None = None
    hotspare: str | None = None  # global/dedicated（storcli）
    failed: bool = False  # storcli PD 故障；mdadm 成员用 faulty
    device: str | None = None  # mdadm 成员分区名（sda2）
    index: int | None = None  # mdadm 成员序号
    faulty: bool = False  # mdadm (F)
    spare: bool = False  # mdadm (S)


class RaidVolumeItem(BaseModel):
    """阵列卷（硬 RAID VD / 软 RAID md，契约 §2.8；details.sync 见契约）。"""
    source: str  # storcli / mdadm
    controller: str
    volume_id: str
    name: str
    level: str
    size_bytes: int | None = None
    state: str
    healthy: bool
    details: dict = {}
    members: list[RaidMemberItem] = []  # 阵列成员（PD 按 DG join / mdstat 解析）


class RaidResponse(BaseModel):
    """阵列响应（硬 RAID + 软 RAID + 控制器 + 物理盘）。"""
    available: bool
    hardware_raid: list[RaidVolumeItem] = []
    software_raid: list[RaidVolumeItem] = []
    storcli_error: str | None = None
    # ↓↓↓ 契约 §2.8 增量字段（只加不改名不删）：Broadcom/LSI 阵列卡控制器与物理盘
    controller: dict | None = None
    drives: list[dict] = []


class VolumeForecast(BaseModel):
    """挂载点写满预测（volume_15m 每 15 分钟回归一次；days_to_full=None=增速≈0）。"""
    """挂载点写满预测（volume_15m 每 15 分钟回归一次；days_to_full=None=增速≈0）。"""

    days_to_full: float | None = None
    slope_percent_per_day: float = 0.0
    last_percent: float
    sampled_hours: int


class VolumeItem(BaseModel):
    """挂载卷（契约 §2.9，含 forecast 写满预测）。"""
    device: str
    mount: str
    fs_type: str
    total_bytes: int
    used_bytes: int
    free_bytes: int
    percent: float
    opts: list[str]
    # 数据不足（接入 <6h）时无预测条目 → None，前端显式"—"
    forecast: VolumeForecast | None = None


class SelfTestIn(BaseModel):
    """发起自检请求体。"""
    device: str = Field(pattern=r"^(nvme)?[a-z0-9]+$|^/dev/(nvme)?[a-z0-9]+$")
    type: str = Field(pattern="^(short|long|conveyance)$")


class SelfTestState(BaseModel):
    """自检任务状态（进程内，重启即失）。"""
    device: str
    type: str
    status: str  # running/done/failed
    started_at: str
    completed_at: str | None = None
    percent: int | None = None
    result: str | None = None
    error: str | None = None


class SmartTrendPoint(BaseModel):
    """SMART 趋势点（smart_15m 采集）。"""
    ts: str
    value: float
    raw_text: str | None = None


class SmartTrendResponse(BaseModel):
    """SMART 趋势序列（days≤30 回 1h 桶，否则 1d 桶）。"""
    device: str
    metric: str
    granularity: str  # 1h（days≤30）/ 1d（更长）
    days: int
    points: list[SmartTrendPoint]
