"""WebSocket 实时推送（契约 §4）：realtime 1s / fans 5s / alert 事件 / pong。

鉴权与 REST 对齐（REST 各路由挂 ApiKeyDep/TrimAuthDep，本端点此前完全裸奔）：
- trim 形态：先 fail-closed 校验 X-Nasdeck-Proxy 代理共享密钥（未配置即拒，
  与 REST require_trim_auth 对齐），通过后再要求 index.cgi 转发的
  X-Trim-Userid 身份头非空；
- api_key 形态：握手须带 ?api_key 查询参数或 X-API-Key 头，经 hmac.compare_digest
  常数时间比较（空值先短路，防 None/空串进入比较函数抛 TypeError）；
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
    """序列化 realtime 快照为推送文本，同一秒的快照复用缓存。

    Args:
        snap (dict): realtime 快照（须含 ts 字段作为缓存键）。

    Returns:
        str: ``{"type": "realtime", "data": snap}`` 的紧凑 JSON 文本。
    """
    key = snap.get("ts")
    if key != _last_snap_text["key"]:
        _last_snap_text["key"] = key
        _last_snap_text["text"] = json.dumps({"type": "realtime", "data": snap}, separators=(",", ":"))
    return _last_snap_text["text"]


def _loopback_bind() -> bool:
    """判断服务是否仅绑定回环地址。"""
    return settings.host in ("127.0.0.1", "localhost", "::1")


def _host_header_name(ws: WebSocket) -> str:
    """从 WS 握手的 Host 头提取主机名。

    Args:
        ws (WebSocket): WebSocket 连接。

    Returns:
        str: 主机名，Host 缺失或无法解析时为空串。
    """
    raw = ws.headers.get("host", "")
    return urlsplit(f"//{raw}").hostname or "" if raw else ""


def _ws_authorized(ws: WebSocket) -> bool:
    """按部署形态校验 WS 握手是否放行（各形态规则见模块 docstring）。

    Args:
        ws (WebSocket): WebSocket 连接。

    Returns:
        bool: 是否通过鉴权。
    """
    if settings.trim_auth:
        # 飞牛形态（评审 2026-10-09 S3，与 REST require_trim_auth 对齐）：先
        # fail-closed 校验代理共享密钥（未配置即拒），再要求 X-Trim-Userid 身份
        # 头非空（防本机进程绕过直连拉数据）
        if not settings.proxy_token:
            return False
        if not hmac.compare_digest(ws.headers.get("x-nasdeck-proxy", ""), settings.proxy_token):
            return False
        return bool(ws.headers.get("x-trim-userid", "").strip())
    if settings.api_key:
        supplied = ws.query_params.get("api_key") or ws.headers.get("x-api-key", "")
        # compare_digest 防时序侧信道；supplied 经 or 链兜底必为 str（query_params
        # 落空时为 None，由 "" 替代），空值先 False 短路避免对 None 比较抛 TypeError
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
    """WS 实时推送主循环：realtime 1s / fans+alerts 5s / ping-pong。

    鉴权失败以 1008 关闭；任一子任务因连接断开退出后取消其余任务并收尾关闭。

    Args:
        ws (WebSocket): WebSocket 连接（框架注入）。
    """
    if not _ws_authorized(ws):
        await ws.close(code=1008)
        return
    await ws.accept()
    stop = asyncio.Event()

    async def push_realtime() -> None:
        """每 1s 推送一条 realtime 快照（缓存缺失时该秒跳过）。"""
        # 连接建立即补发一条（缓存存在时），之后每 1s；同秒快照共享同一份序列化文本
        while not stop.is_set():
            snap = realtime_cache.get("realtime")
            if snap is not None:
                await ws.send_text(_snapshot_text(snap))
            await asyncio.sleep(1)

    async def push_fans_and_alerts() -> None:
        """每 5s 推送风扇输出与连接期内未推送的告警事件。"""
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
        """接收客户端消息：收到 ping 回 pong；连接断开时触发全局停止。"""
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
        # 先完成关闭握手再回收推送任务：推送方可能正阻塞在 send 上，先取消会
        # 中止传输层导致 close 帧发不出去，客户端退出时等待关闭完成而超时/取消
        with contextlib.suppress(Exception):
            await ws.close()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
