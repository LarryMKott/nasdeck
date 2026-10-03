"""WebSocket 实时推送（契约 §4）：realtime 1s / fans 5s / alert 事件 / pong。

鉴权与 REST 对齐（REST 各路由挂 ApiKeyDep/TrimAuthDep，本端点此前完全裸奔）：
- trim 形态：要求 index.cgi 转发的 X-Trim-Userid 身份头；
- api_key 形态：握手须带 ?api_key= 或 X-API-Key 头；
- 无鉴权形态：校验 Origin 与 Host 同源（浏览器跨站可不受 CORS 约束发起 WS），
  绑定回环时不校验（开发机 vite 代理 changeOrigin 会改写 Host）。
非浏览器客户端不发 Origin，允许直连（运维脚本场景）。
fnOS 网关穿透性待真机验证，前端保留轮询降级。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from urllib.parse import urlsplit

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.services.monitor.cache import realtime_cache

logger = logging.getLogger(__name__)
router = APIRouter()

# 同一秒的快照对象全连接共享，序列化一次（N 客户端 = 1 次 dumps/秒，而非 N 次）
_last_snap_text = {"key": None, "text": ""}


def _snapshot_text(snap: dict) -> str:
    key = snap.get("ts")
    if key != _last_snap_text["key"]:
        _last_snap_text["key"] = key
        _last_snap_text["text"] = json.dumps({"type": "realtime", "data": snap}, separators=(",", ":"))
    return _last_snap_text["text"]


def _loopback_bind() -> bool:
    return settings.host in ("127.0.0.1", "localhost", "::1")


def _host_header_name(ws: WebSocket) -> str:
    raw = ws.headers.get("host", "")
    return urlsplit(f"//{raw}").hostname or "" if raw else ""


def _ws_authorized(ws: WebSocket) -> bool:
    if settings.trim_auth:
        # 飞牛形态：无 X-Trim-Userid 身份头的连接直接拒（防本机进程绕过直连拉数据）
        return bool(ws.headers.get("x-trim-userid", "").strip())
    if settings.api_key:
        supplied = ws.query_params.get("api_key") or ws.headers.get("x-api-key", "")
        return bool(supplied) and supplied == settings.api_key
    if _loopback_bind():
        return True
    origin = ws.headers.get("origin")
    if not origin:
        return True
    try:
        origin_host = urlsplit(origin).hostname
    except ValueError:
        return False
    return bool(origin_host) and origin_host == _host_header_name(ws)


@router.websocket("/api/v1/ws/realtime")
async def realtime_ws(ws: WebSocket) -> None:
    if not _ws_authorized(ws):
        await ws.close(code=1008)
        return
    await ws.accept()
    stop = asyncio.Event()

    async def push_realtime() -> None:
        # 连接建立即补发一条（缓存存在时），之后每 1s；同秒快照共享同一份序列化文本
        while not stop.is_set():
            snap = realtime_cache.get("realtime")
            if snap is not None:
                await ws.send_text(_snapshot_text(snap))
            await asyncio.sleep(1)

    async def push_fans_and_alerts() -> None:
        sent_alerts: set[int] = set()
        while not stop.is_set():
            fans = realtime_cache.get("fan_outputs")
            if fans:
                await ws.send_json({"type": "fans", "data": fans})
            for event in realtime_cache.get("latest_alert_events") or []:
                if event["id"] not in sent_alerts:
                    sent_alerts.add(event["id"])
                    await ws.send_json(
                        {
                            "type": "alert",
                            "data": {
                                "id": event["id"],
                                "rule_name": event["rule_name"],
                                "status": event["status"],
                                "severity": event["severity"],
                                "message": event["message"],
                            },
                        }
                    )
            await asyncio.sleep(5)

    async def recv() -> None:
        try:
            while True:
                message = await ws.receive_text()
                if message == "ping":
                    await ws.send_json({"type": "pong"})
        except (WebSocketDisconnect, RuntimeError):
            stop.set()

    tasks = [asyncio.create_task(coro()) for coro in (push_realtime, push_fans_and_alerts, recv)]
    try:
        await stop.wait()
    finally:
        stop.set()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        with contextlib.suppress(Exception):
            await ws.close()
