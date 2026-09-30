"""监控指标历史模型：1s 原始点 + 1m/10m 聚合点同表，以 granularity 区分。"""

from __future__ import annotations

from sqlalchemy import Float, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MetricPoint(Base):
    __tablename__ = "metric_points"
    __table_args__ = (UniqueConstraint("ts", "granularity", name="uq_ts_granularity"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(String(20), index=True)  # 无时区后缀 UTC ISO（契约 §1.5）
    granularity: Mapped[str] = mapped_column(String(4), default="raw", index=True)  # raw/1m/10m
    cpu: Mapped[float | None] = mapped_column(Float)
    mem_mb: Mapped[float | None] = mapped_column(Float)
    net_kbps: Mapped[float | None] = mapped_column(Float)
    temp_max: Mapped[float | None] = mapped_column(Float)
    gpu: Mapped[float | None] = mapped_column(Float)  # 实时未接入，暂恒 NULL（契约 §6.1）
    disk_read_kbps: Mapped[float | None] = mapped_column(Float)
    disk_write_kbps: Mapped[float | None] = mapped_column(Float)
