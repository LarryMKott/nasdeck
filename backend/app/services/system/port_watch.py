"""监听端口异动监视（M3.3）：对比前后两轮 LISTEN 集合，新端口且无标注即告警。

安全向哨兵：陌生服务开监听往往早于可见的入侵痕迹。已知端口白名单 =
port_aliases 表（用户标注过的端口视为已知）。每端口 24h 去重窗抑制抖动；
首轮只建基线（升级/重启窗口的存量监听不轰炸）。60s 一拍由 slow_60s 驱动。
"""

from __future__ import annotations

import logging
import socket
import time

import psutil
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system import PortAlias

logger = logging.getLogger(__name__)

DEDUP_SECONDS = 24 * 3600
_prev_listen: set[tuple[str, int]] = set()  # (proto, port)
_last_alert: dict[tuple[str, int], float] = {}
_baseline_done = False


def reset_for_test() -> None:
    global _baseline_done
    _prev_listen.clear()
    _last_alert.clear()
    _baseline_done = False


def _current_listen() -> set[tuple[str, int]]:
    """当前 LISTEN (proto, port) 集合；端口取 laddr.port（任意地址/具体地址归并）。"""
    listen: set[tuple[str, int]] = set()
    for conn in psutil.net_connections(kind="inet"):
        if conn.status != psutil.CONN_LISTEN or not conn.laddr:
            continue
        proto = "udp" if conn.type == socket.SOCK_DGRAM else "tcp"
        listen.add((proto, conn.laddr.port))
    return listen


async def watch_tick(db: AsyncSession) -> list[dict]:
    """一轮对比，返回需告警的新监听端口 [{proto, port}]。

    Args:
        db (AsyncSession): 请求级/任务级会话（读 port_aliases 白名单）。

    Returns:
        list[dict]: 新增且无标注的监听端口（已按 24h 去重窗过滤）。
    """
    global _baseline_done, _prev_listen
    current = _current_listen()
    if not _baseline_done:
        # 首轮基线：存量监听不告警（升级/重启窗口防轰炸）
        _prev_listen = current
        _baseline_done = True
        return []

    result = await db.execute(select(PortAlias.port))
    known = {row[0] for row in result.all()}

    now = time.monotonic()
    events = []
    for proto, port in sorted(current - _prev_listen):
        if port in known:
            continue  # 用户标注过的端口视为已知（白名单）
        if now - _last_alert.get((proto, port), float("-inf")) < DEDUP_SECONDS:
            continue
        _last_alert[(proto, port)] = now
        events.append({"proto": proto, "port": port})
    _prev_listen = current
    return events


async def persist_and_notify(db: AsyncSession, events: list[dict]) -> None:
    """异动事件落事件历史并向全部启用渠道广播。调用方负责 commit。

    Args:
        db (AsyncSession): 任务级会话。
        events (list[dict]): watch_tick 输出。
    """
    from datetime import UTC, datetime

    from app.models.alert import AlertEvent
    from app.services.alert import engine as alert_engine

    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    for e in events:
        message = f"发现新的 {e['proto'].upper()} 监听端口 {e['port']}（无标注，非已知服务）"
        db.add(
            AlertEvent(
                rule_id=None,
                rule_name="端口异动",
                metric="port_new",
                value=float(e["port"]),
                threshold=None,
                severity="warning",
                status="resolved",
                message=message,
                fired_at=now,
                resolved_at=now,
            )
        )
        await alert_engine.notify_broadcast(db, title=f"端口异动 · {e['port']}", body=message)
    await db.flush()
