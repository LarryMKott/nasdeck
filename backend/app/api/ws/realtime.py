"""WebSocket 实时推送（契约 §4）：realtime 1s / fans 5s / alert 事件 / pong。

鉴权与 REST 对齐（REST 各路由挂 ApiKeyDep/TrimAuthDep，本端点此前完全裸奔）：
- trim 形态：要求 index.cgi 转发的 X-Trim-Userid 身份头，且代理共享密钥
  X-Nasdeck-Proxy 与 REST 同口径 compare_digest 校验（此前仅查 userid 存在，
  本机进程伪造头即可直连拉全量实时数据——评审 2026-10-25 P1-01）；
- api_key 形态：握手须带 ?api_key= 或 X-API-Key 头（compare_digest，防时序侧信道）；
- 无鉴权形态：校验 Origin 与 Host 同源（浏览器跨站可不受 CORS 约束发起 WS），
  绑定回环时不校验（开发机 vite 代理 changeOrigin 会改写 Host）。
非浏览器客户端不发 Origin，允许直连（运维脚本场景）。
fnOS 网关穿透性待真机验证，前端保留轮询降级。
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
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
        # 代理共享密钥根防线：与 REST 侧 require_trim_auth 同口径（密钥未配置时
        # 退化为仅查 userid，启动日志已有显式 warning）
        if settings.proxy_token and not hmac.compare_digest(
            ws.headers.get("x-nasdeck-proxy", ""), settings.proxy_token
        ):
            return False
        return bool(ws.headers.get("x-trim-userid", "").strip())
    if settings.api_key:
        supplied = ws.query_params.get("api_key") or ws.headers.get("x-api-key", "")
        return bool(supplied) and hmac.compare_digest(supplied, settings.api_key)
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

    async def _guarded(name: str, coro_fn) -> None:
        # push/recv 任务异常不得静默死亡：置位 stop 让整个 handler 收尾，
        # 否则连接变"僵尸推送"或 handler 永久挂起泄漏（评审 P1-9）
        try:
            await coro_fn()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("WS %s 任务异常退出，关闭连接", name, exc_info=True)
            stop.set()

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
        # 按消息类型分派：receive_text 遇二进制帧抛 KeyError 且不在常规捕获内，
        # 曾致 handler 永久挂起泄漏连接（评审 P1-9）
        try:
            while True:
                message = await ws.receive()
                if message["type"] == "websocket.disconnect":
                    break
                if message.get("text") == "ping":
                    await ws.send_json({"type": "pong"})
        except (WebSocketDisconnect, RuntimeError, KeyError):
            pass
        finally:
            stop.set()

    tasks = [
        asyncio.create_task(_guarded(name, coro))
        for name, coro in (("push_realtime", push_realtime), ("push_fans", push_fans_and_alerts), ("recv", recv))
    ]
    try:
        await stop.wait()
    finally:
        stop.set()
        for task in tasks:
            task.cancel()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for res in results:
            if isinstance(res, BaseException) and not isinstance(res, asyncio.CancelledError):
                logger.warning("WS 任务收尾异常: %r", res)
        with contextlib.suppress(Exception):
            await ws.close()
