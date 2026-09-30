"""ORM 基类与公共字段。"""

from __future__ import annotations

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[str] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )
