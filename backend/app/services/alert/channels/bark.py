"""Bark 渠道：iOS 推送（GET/{server}/{key}/{title}/{body}）。"""

from __future__ import annotations

from urllib.parse import quote

import httpx

from app.services.alert.channels.base import BaseChannel


class BarkChannel(BaseChannel):
    type = "bark"

    def required_fields(self) -> list[str]:
        return ["device_key"]

    async def send(self, config: dict, title: str, body: str) -> bool:
        server = config.get("server", "https://api.day.app").rstrip("/")
        # 路径段必须全编码：title/body 含 / ? # 时裸拼会改变路径结构或截断消息
        key = quote(str(config["device_key"]), safe="")
        t = quote(str(title), safe="")
        b = quote(str(body), safe="")
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{server}/{key}/{t}/{b}",
                )
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
