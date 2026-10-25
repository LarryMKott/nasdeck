"""Bark 渠道：iOS 推送（GET/{server}/{key}/{title}/{body}）。"""

from __future__ import annotations

import logging
from urllib.parse import quote

import httpx

from app.core.exceptions import InvalidParamsError
from app.services.alert.channels.base import BaseChannel
from app.utils.net_guard import assert_public_url

logger = logging.getLogger(__name__)

_DEFAULT_SERVER = "https://api.day.app"


class BarkChannel(BaseChannel):
    type = "bark"

    def required_fields(self) -> list[str]:
        return ["device_key"]

    def validate(self, config: dict) -> None:
        super().validate(config)
        # server 可省略（默认官方），自建 server 必须是公网 http(s)（SSRF 护栏）
        assert_public_url(config.get("server", _DEFAULT_SERVER), what="bark server")

    async def send(self, config: dict, title: str, body: str) -> str | None:
        server = config.get("server", _DEFAULT_SERVER).rstrip("/")
        # 路径段必须全编码：title/body 含 / ? # 时裸拼会改变路径结构或截断消息
        key = quote(str(config["device_key"]), safe="")
        t = quote(str(title), safe="")
        b = quote(str(body), safe="")
        try:
            # 发送时复检：防保存后 DNS 被改指向内网
            assert_public_url(server, what="bark server")
        except InvalidParamsError as exc:
            logger.warning("bark 发送被 SSRF 护栏拒绝: %s", exc)
            return "ssrf_rejected"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{server}/{key}/{t}/{b}",
                )
                return None if resp.status_code == 200 else "bad_response"
        except httpx.TimeoutException:
            return "timeout"
        except httpx.HTTPError:
            return "network"
