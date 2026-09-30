"""系统域模型：端口标注、终止白名单、系统设置。"""

from __future__ import annotations

from sqlalchemy import JSON, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class PortAlias(Base, TimestampMixin):
    __tablename__ = "port_aliases"
    __table_args__ = (UniqueConstraint("port", name="uq_port"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    port: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(64))
    note: Mapped[str] = mapped_column(String(255), default="")


class KillWhitelist(Base, TimestampMixin):
    __tablename__ = "kill_whitelist"
    __table_args__ = (UniqueConstraint("name", name="uq_whitelist_name"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)


class SystemSetting(Base, TimestampMixin):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON, default=None)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
