"""系统域模型：端口标注、终止白名单、系统设置。"""

from __future__ import annotations

from sqlalchemy import JSON, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class PortAlias(Base, TimestampMixin):
    """端口标注：用户给监听端口起的名字/备注（端口页展示）。

    Attributes:
        port (int): 端口号（唯一）。
        label (str): 端口名（如 "WebUI"）。
        note (str): 备注。
    """

    __tablename__ = "port_aliases"
    __table_args__ = (UniqueConstraint("port", name="uq_port"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    port: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(64))
    note: Mapped[str] = mapped_column(String(255), default="")


class KillWhitelist(Base, TimestampMixin):
    """进程终止保护名单：名单内进程拒绝 kill（一键释放的安全防线）。

    Attributes:
        name (str): 进程名（唯一，精确匹配）。
        reason (str | None): 保护原因（前端提示）。
    """

    __tablename__ = "kill_whitelist"
    __table_args__ = (UniqueConstraint("name", name="uq_whitelist_name"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)


class SystemSetting(Base, TimestampMixin):
    """系统设置 KV：巡检计划/静音计划/迁移标记等持久化键值。

    Attributes:
        key (str): 设置键（主键；如 selftest_schedule / fan_schedule）。
        value (dict | list | str | int | float | bool | None): JSON 值（结构由各键自约定）。
        description (str | None): 键用途说明（GET /settings 透出）。
    """

    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON, default=None)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)


class ContainerPoint(Base, TimestampMixin):
    """容器资源 1m 桶（花活二期 M）：CPU/内存/磁盘 IO 趋势，保留 7 天。

    Attributes:
        ts (str): 整分桶键（UTC 墙钟串，口径同 MetricPoint）。
        name (str): 容器名（同桶覆盖写键之一）。
        cpu_percent (float | None): 全核口径 CPU%；首采无增量为 null。
        mem_mb (float | None): working set MB。
        read_kbps / write_kbps (float | None): cgroup v2 io.stat 差分 KB/s；
            v1/无 io.stat 为 null（前端显"—"）。
    """

    __tablename__ = "container_points"
    __table_args__ = (UniqueConstraint("ts", "name", name="uq_container_point"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(64), index=True)
    cpu_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    mem_mb: Mapped[float | None] = mapped_column(Float, nullable=True)
    read_kbps: Mapped[float | None] = mapped_column(Float, nullable=True)
    write_kbps: Mapped[float | None] = mapped_column(Float, nullable=True)
