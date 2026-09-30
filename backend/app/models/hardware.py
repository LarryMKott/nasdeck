"""硬件基础信息模型：慢采集落库，报告/未来 /hardware/* 只读接口使用。"""

from __future__ import annotations

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class HardwareItem(Base, TimestampMixin):
    __tablename__ = "hardware_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)  # cpu/gpu/memory/board/nic/raid_card
    name: Mapped[str] = mapped_column(String(255), default="")
    props: Mapped[dict] = mapped_column(JSON, default=dict)  # 采集器输出的逐字段属性
