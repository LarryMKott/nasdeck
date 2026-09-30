"""系统域 DTO：主机信息 / Docker / 端口 / 进程 / 白名单 / 设置（契约 §2.10-2.14）。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SystemInfo(BaseModel):
    hostname: str
    platform: str
    kernel: str
    machine: str
    python: str
    os_release: str
    fnos_version: str | None = None
    uptime_s: int
    app_version: str


class ContainerItem(BaseModel):
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
    available: bool
    reason: str | None = None
    containers: list[ContainerItem] = []


class PortEntry(BaseModel):
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
    port: int = Field(ge=1, le=65535)
    label: str = Field(min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=255)


class PortAliasOut(BaseModel):
    id: int
    port: int
    label: str
    note: str | None = None


class ProcessItem(BaseModel):
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
    name: str = Field(min_length=1, max_length=128)
    reason: str | None = Field(default=None, max_length=255)


class WhitelistItem(BaseModel):
    id: int
    name: str
    reason: str | None = None


class DeletedOut(BaseModel):
    id: int
    deleted: bool


class SettingPut(BaseModel):
    value: Any
    description: str | None = None


class SettingEntry(BaseModel):
    value: Any
    description: str | None = None
