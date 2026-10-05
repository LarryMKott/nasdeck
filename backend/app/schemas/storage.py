"""存储域 DTO：磁盘 / SMART / 自检 / 阵列 / 卷（契约 §2.5-2.9）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PartitionItem(BaseModel):
    name: str  # 不带 /dev/ 前缀（sda1 / dm-0）
    size_bytes: int | None = None
    fstype: str | None = None
    mountpoint: str | None = None
    type: str = "part"  # part/lvm/crypt…（lsblk TYPE，非分区形态平铺展示）


class DiskItem(BaseModel):
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
    partitions: list[PartitionItem] = []  # lsblk children 平铺（拓扑树层级边）


class SmartAttribute(BaseModel):
    id: int
    name: str
    value: int | None
    worst: int | None
    threshold: int | None
    raw: str | None


class SmartReport(BaseModel):
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
    alias: str = Field(min_length=1, max_length=64)


class AliasOut(BaseModel):
    serial: str
    alias: str | None = None


class AliasDeleted(BaseModel):
    serial: str
    deleted: bool


class RaidMemberItem(BaseModel):
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
    available: bool
    hardware_raid: list[RaidVolumeItem] = []
    software_raid: list[RaidVolumeItem] = []
    storcli_error: str | None = None
    # ↓↓↓ 契约 §2.8 增量字段（只加不改名不删）：Broadcom/LSI 阵列卡控制器与物理盘
    controller: dict | None = None
    drives: list[dict] = []


class VolumeItem(BaseModel):
    device: str
    mount: str
    fs_type: str
    total_bytes: int
    used_bytes: int
    free_bytes: int
    percent: float
    opts: list[str]


class SelfTestIn(BaseModel):
    device: str = Field(pattern=r"^(nvme)?[a-z0-9]+$|^/dev/(nvme)?[a-z0-9]+$")
    type: str = Field(pattern="^(short|long|conveyance)$")


class SelfTestState(BaseModel):
    device: str
    type: str
    status: str  # running/done/failed
    started_at: str
    completed_at: str | None = None
    percent: int | None = None
    result: str | None = None
    error: str | None = None


class SmartTrendPoint(BaseModel):
    ts: str
    value: float
    raw_text: str | None = None


class SmartTrendResponse(BaseModel):
    device: str
    metric: str
    granularity: str  # 1h（days≤30）/ 1d（更长）
    days: int
    points: list[SmartTrendPoint]
