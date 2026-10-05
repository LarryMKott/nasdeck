"""监控指标历史模型：1s 原始点 + 1m/10m 聚合点同表，以 granularity 区分。"""

from __future__ import annotations

from sqlalchemy import Float, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MetricPoint(Base):
    """系统指标历史点：秒级原始与分钟聚合同表，granularity 区分（raw/1m/10m）。

    Attributes:
        ts (str): UTC 墙钟串（契约 §1.5）；聚合行为对齐桶起点。
        granularity (str): raw / 1m / 10m。
        cpu / mem_mb / net_kbps / temp_max / gpu / disk_read_kbps / disk_write_kbps:
            各指标值；无数据源的列为 NULL（不造 0 值）。
    """

    __tablename__ = "metric_points"
    __table_args__ = (
        UniqueConstraint("ts", "granularity", name="uq_ts_granularity"),
        # 热点查询全是 WHERE granularity=? AND ts 区间（history/downsampler 的
        # SELECT 与 DELETE）：复合索引直达；原 ts/granularity 单列索引冗余
        # （ts 被 uq 最左前缀覆盖、granularity 仅 3 个值），见 init_db 幂等收敛
        Index("ix_metric_points_gran_ts", "granularity", "ts"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(String(20))  # 无时区后缀 UTC ISO（契约 §1.5）
    granularity: Mapped[str] = mapped_column(String(4), default="raw")  # raw/1m/10m
    cpu: Mapped[float | None] = mapped_column(Float)
    mem_mb: Mapped[float | None] = mapped_column(Float)
    net_kbps: Mapped[float | None] = mapped_column(Float)
    temp_max: Mapped[float | None] = mapped_column(Float)
    gpu: Mapped[float | None] = mapped_column(Float)  # 实时未接入，暂恒 NULL（契约 §6.1）
    disk_read_kbps: Mapped[float | None] = mapped_column(Float)
    disk_write_kbps: Mapped[float | None] = mapped_column(Float)
