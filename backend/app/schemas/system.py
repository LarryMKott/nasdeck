"""系统域 DTO：主机信息 / Docker / 端口 / 进程 / 白名单 / 设置（契约 §2.10-2.14）。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SystemInfo(BaseModel):
    """主机信息（identity 权限判定数据源）。"""
    hostname: str
    platform: str
    kernel: str
    machine: str
    python: str
    os_release: str
    fnos_version: str | None = None
    uptime_s: int
    app_version: str
    # trim 形态下当前登录者是否管理员（透传飞牛注入的 X-Trim-Isadmin 头）；
    # 非 trim 形态（api_key/无鉴权）恒 true——写权限由 api_key 持有者天然具备
    is_admin: bool = True


class ContainerItem(BaseModel):
    """Docker 容器条目（含 cgroup 直读资源用量）。"""
    id: str  # 12 位短 id
    name: str
    image: str
    state: str
    status: str
    created: str
    ports: list[str] = []
    cpu_percent: float | None = None
    mem_usage: str | None = None


class DockerResponse(BaseModel):
    """容器清单响应（available=false 时 reason 带原因）。"""
    available: bool
    reason: str | None = None
    containers: list[ContainerItem] = []


class PortEntry(BaseModel):
    """监听/连接端口条目。"""
    proto: str  # tcp/udp
    local_addr: str
    local_port: int
    remote_addr: str | None = None
    remote_port: int | None = None
    status: str
    pid: int | None = None
    process: str | None = None
    alias: str | None = None


class PortAliasIn(BaseModel):
    """端口标注写入请求体。"""
    port: int = Field(ge=1, le=65535)
    label: str = Field(min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=255)


class PortAliasOut(BaseModel):
    """端口标注响应。"""
    id: int
    port: int
    label: str
    note: str | None = None


class ProcessItem(BaseModel):
    """进程条目（释放功能展示用）。"""
    pid: int
    name: str
    exe: str | None = None
    cmdline: str | None = None
    user: str | None = None
    cpu_percent: float
    mem_percent: float
    mem_rss_mb: float
    status: str
    protected: bool


class WhitelistIn(BaseModel):
    """终止保护名单写入请求体（同名即更新）。"""
    name: str = Field(min_length=1, max_length=128)
    reason: str | None = Field(default=None, max_length=255)


class WhitelistItem(BaseModel):
    """保护名单条目。"""
    id: int
    name: str
    reason: str | None = None


class DeletedOut(BaseModel):
    """通用删除成功响应。"""

    id: int
    deleted: bool


class SettingPut(BaseModel):
    """系统设置写入请求体（upsert）。"""
    value: Any
    description: str | None = None


class SelftestScheduleIn(BaseModel):
    """SMART 周期巡检计划（PUT 仅管理员）。weekday 0=周一；type 仅 short/long。"""
    """SMART 周期巡检计划（PUT 仅管理员）。weekday 0=周一；type 仅 short/long。"""

    enabled: bool
    weekday: int = Field(ge=0, le=6)
    hour: int = Field(ge=0, le=23)
    type: str = Field(pattern="^(short|long)$")


class SelftestScheduleOut(SelftestScheduleIn):
    """巡检计划响应（含 last_run）。"""
    last_run: str | None = None  # ISO 日期（YYYY-MM-DD）；未跑过为 null


class SettingEntry(BaseModel):
    """系统设置条目。"""
    value: Any
    description: str | None = None
