"""ORM 基类与公共字段。"""

from __future__ import annotations

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """全部 ORM 模型的声明基类。

    metadata 由 init_db 显式导入各模型模块注册（models/__init__ 为空，未导入
    的模块其表不会进入 Base.metadata——曾致 hardware 表重建 KeyError）。
    """


class TimestampMixin:
    """行创建时间混入（UTC，由 SQLite current_timestamp 服务端生成）。

    Attributes:
        created_at (str): 行创建时间；导出/审计与"建表即有关键列"识别共用。
    """

    created_at: Mapped[str] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )
