"""存储域模型：磁盘别名（按 serial 持久化）、SMART/容量趋势点。自检状态为进程内状态不入库。"""

from __future__ import annotations

from sqlalchemy import Float, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class DiskAlias(Base, TimestampMixin):
    """磁盘别名：用户给物理盘起的好记名字（按序列号持久化）。

    Attributes:
        serial (str): 盘序列号（唯一键）。
        alias (str): 别名（硬盘页/拓扑树展示）。
    """

    __tablename__ = "disk_aliases"
    __table_args__ = (UniqueConstraint("serial", name="uq_disk_serial"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    serial: Mapped[str] = mapped_column(String(64))
    alias: Mapped[str] = mapped_column(String(64))


class SmartPoint(Base, TimestampMixin):
    """SMART 指标趋势点：15m 采样整桶覆盖写 1h/1d 两级桶（SMART 变化慢，
    不进 metric_points；桶键 UTC 墙钟串，口径同 MetricPoint，契约 §1.5）。"""

    __tablename__ = "smart_points"
    __table_args__ = (
        UniqueConstraint("ts", "granularity", "device", "metric", name="uq_smart_bucket"),
        Index("ix_smart_points_gran_dev_metric_ts", "granularity", "device", "metric", "ts"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(String(20))  # 桶起点（1h=整点 / 1d=当日 00:00 UTC）
    granularity: Mapped[str] = mapped_column(String(4))  # 1h / 1d
    device: Mapped[str] = mapped_column(String(24))  # SMART 探测键（sda / nvme0）
    # reallocated/pending/uncorrectable/wear_leveling/temp_c/percent_used/
    # media_errors/power_on_hours（ATA 按 attribute id，NVMe 取健康日志字段）
    metric: Mapped[str] = mapped_column(String(24))
    value: Mapped[float] = mapped_column(Float)
    raw_text: Mapped[str | None] = mapped_column(String(32), nullable=True)  # ATA 原始串


class VolumePoint(Base, TimestampMixin):
    """容量趋势点：1h 桶（容量变化慢），供 14 天线性回归预测写满时间。"""

    __tablename__ = "volume_points"
    __table_args__ = (
        UniqueConstraint("ts", "mount", name="uq_volume_bucket"),
        Index("ix_volume_points_mount_ts", "mount", "ts"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(String(20))  # 整点桶 UTC ISO
    mount: Mapped[str] = mapped_column(String(128))
    used_gb: Mapped[float] = mapped_column(Float)
    total_gb: Mapped[float] = mapped_column(Float)
