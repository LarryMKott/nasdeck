"""端口占用识别与管理：psutil 连接表 + 端口标注合并（契约 §2.12）。"""

from __future__ import annotations

import ipaddress
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


# 星图内网归类（花活二期 L）：RFC1918 + 环回 + 链路本地 + ULA；不引 GeoIP 不出网
_LAN_NETS = tuple(
    ipaddress.ip_network(n)
    for n in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "::1/128",
        "fe80::/10",
        "fc00::/7",
    )
)


def _is_lan(ip: str) -> bool:
    """远端 IP 是否内网（RFC1918/环回/链路本地/ULA）；解析失败按外网计。"""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in _LAN_NETS)


def network_map() -> dict:
    """星图数据面（花活二期 L）：一次 psutil 连接表扫描的聚合视图。

    Returns:
        dict: {listening, established, lan, wan, remotes}；remotes 为远端
            IP 聚合（最多 24 条按连接数降序），每项 {ip, lan, count}——
            只计数与聚合 IP，不列端口/进程详情（隐私口径同 §2.12）。
    """
    conns = psutil.net_connections(kind="inet")
    listening = 0
    lan = wan = 0
    remotes: dict[str, dict] = {}
    for c in conns:
        if c.status == psutil.CONN_LISTEN:
            listening += 1
            continue
        if c.status != psutil.CONN_ESTABLISHED or not c.raddr:
            continue
        ip = c.raddr.ip
        is_lan = _is_lan(ip)
        if is_lan:
            lan += 1
        else:
            wan += 1
        agg = remotes.setdefault(ip, {"ip": ip, "lan": is_lan, "count": 0})
        agg["count"] += 1
    return {
        "listening": listening,
        "established": lan + wan,
        "lan": lan,
        "wan": wan,
        "remotes": sorted(remotes.values(), key=lambda r: -r["count"])[:24],
    }
