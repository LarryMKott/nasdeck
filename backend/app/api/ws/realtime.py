"""WebSocket 实时推送（契约 §4）：realtime 1s / fans 5s / alert 事件 / pong。

当前无鉴权（契约注明）；fnOS 网关穿透性待真机验证，前端保留轮询降级。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.monitor.cache import realtime_cache

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/api/v1/ws/realtime")
async def realtime_ws(ws: WebSocket) -> None:
    await ws.accept()
    stop = asyncio.Event()

    async def push_realtime() -> None:
        # 连接建立即补发一条（缓存存在时），之后每 1s
        while not stop.is_set():
            snap = realtime_cache.get("realtime")
            if snap is not None:
                await ws.send_json({"type": "realtime", "data": snap})
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
