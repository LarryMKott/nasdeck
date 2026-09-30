"""存储域模型：磁盘别名（按 serial 持久化）。自检状态为进程内状态不入库。"""

from __future__ import annotations

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class DiskAlias(Base, TimestampMixin):
    __tablename__ = "disk_aliases"
    __table_args__ = (UniqueConstraint("serial", name="uq_disk_serial"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    serial: Mapped[str] = mapped_column(String(64))
    alias: Mapped[str] = mapped_column(String(64))
