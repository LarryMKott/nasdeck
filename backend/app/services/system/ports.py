"""端口占用识别与管理：psutil 连接表 + 端口标注合并（契约 §2.12）。"""

from __future__ import annotations

import socket

import psutil
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system import PortAlias


async def list_ports(db: AsyncSession) -> list[dict]:
    """端口占用清单：psutil 连接表逐条合并端口标注与进程名。

    Args:
        db (AsyncSession): 请求级会话（读 PortAlias 标注）。

    Returns:
        list[dict]: 按 local_port 升序的连接条目，每项含 proto/local_addr/
        local_port/remote_addr/remote_port/status/pid/process/alias。
    """
    result = await db.execute(select(PortAlias))
    alias_map = {row.port: row.label for row in result.scalars()}

    proc_names: dict[int, str] = {}
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            proc_names[proc.info["pid"]] = proc.info["name"] or ""
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    entries = []
    seen = set()
    for conn in psutil.net_connections(kind="inet"):
        if conn.status == "NONE":
            continue
        if not conn.laddr:
            continue
        key = (
            conn.proto_name() if hasattr(conn, "proto_name") else "tcp",
            conn.laddr.ip,
            conn.laddr.port,
            conn.status,
            conn.pid,
        )
        if key in seen:
            continue
        seen.add(key)
        # IntEnum 直接比较：py3.11+ str(SocketKind) 返回数值，字符串后缀判断恒 False
        # （曾导致所有 UDP 监听被标成 tcp）
        proto = "udp" if conn.type == socket.SOCK_DGRAM else "tcp"
        entries.append(
            {
                "proto": proto,
                "local_addr": conn.laddr.ip,
                "local_port": conn.laddr.port,
                "remote_addr": conn.raddr.ip if conn.raddr else None,
                "remote_port": conn.raddr.port if conn.raddr else None,
                "status": conn.status,
                "pid": conn.pid,
                "process": proc_names.get(conn.pid) if conn.pid else None,
                "alias": alias_map.get(conn.laddr.port),
            }
        )
    return sorted(entries, key=lambda e: e["local_port"])


async def upsert_alias(db: AsyncSession, port: int, label: str, note: str | None) -> PortAlias:
    """新建或更新端口标注（按端口号 upsert）。

    Args:
        db (AsyncSession): 请求级会话（调用方 commit）。
        port (int): 端口号（唯一键）。
        label (str): 端口标签。
        note (str | None): 备注文案；None 时存空串。

    Returns:
        PortAlias: 落库后的标注行。
    """
    result = await db.execute(select(PortAlias).where(PortAlias.port == port))
    row = result.scalar_one_or_none()
    if row:
        row.label, row.note = label, note or ""
    else:
        row = PortAlias(port=port, label=label, note=note or "")
        db.add(row)
    await db.flush()
    return row
