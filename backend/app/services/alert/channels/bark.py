"""Bark 渠道：iOS 推送（GET/{server}/{key}/{title}/{body}）。"""

from __future__ import annotations

import httpx

from app.services.alert.channels.base import BaseChannel


class BarkChannel(BaseChannel):
    type = "bark"

    def required_fields(self) -> list[str]:
        return ["device_key"]

    async def send(self, config: dict, title: str, body: str) -> bool:
        server = config.get("server", "https://api.day.app").rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{server}/{config['device_key']}/{title}/{body}",
                )
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
