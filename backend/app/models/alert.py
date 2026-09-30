"""告警域模型：规则、通知渠道（config 明文入库，读接口脱敏）、事件。"""

from __future__ import annotations

from sqlalchemy import JSON, Boolean, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class AlertRule(Base, TimestampMixin):
    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64))
    # cpu_percent/mem_percent/temp_max/disk_temp/disk_failed/raid_degraded
    metric: Mapped[str] = mapped_column(String(32))
    comparator: Mapped[str] = mapped_column(String(2))  # > < >= <= ==
    threshold: Mapped[float] = mapped_column(Float)
    duration_ticks: Mapped[int] = mapped_column(Integer, default=1)  # 1-1440 连续满足次数
    severity: Mapped[str] = mapped_column(String(8), default="warning")  # info/warning/critical
    channels: Mapped[list] = mapped_column(JSON, default=list)  # channel_id 列表
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class AlertChannel(Base, TimestampMixin):
    __tablename__ = "alert_channels"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64))
    type: Mapped[str] = mapped_column(String(16))  # telegram/bark/email
    config: Mapped[dict] = mapped_column(JSON, default=dict)  # 明文入库，读接口脱敏
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class AlertEvent(Base, TimestampMixin):
    __tablename__ = "alert_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    rule_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    rule_name: Mapped[str] = mapped_column(String(64), default="")
    metric: Mapped[str] = mapped_column(String(32), default="")
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    severity: Mapped[str] = mapped_column(String(8), default="warning")
    status: Mapped[str] = mapped_column(String(8), default="firing", index=True)  # firing/resolved
    message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    fired_at: Mapped[str] = mapped_column(String(32), default="")
    resolved_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
