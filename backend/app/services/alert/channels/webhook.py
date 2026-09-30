"""Webhook 渠道：POST JSON 到自定义 URL（契约 §2.19/§3.5）。"""

from __future__ import annotations

import httpx

from app.core.exceptions import InvalidParamsError
from app.services.alert.channels.base import BaseChannel


class WebhookChannel(BaseChannel):
    type = "webhook"

    def required_fields(self) -> list[str]:
        return ["url"]

    def validate(self, config: dict) -> None:
        super().validate(config)
        if not str(config["url"]).startswith(("http://", "https://")):
            raise InvalidParamsError("webhook url 须为 http(s) 地址")

    async def send(self, config: dict, title: str, body: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    config["url"],
                    json={"source": "nasdeck", "title": title, "body": body},
                )
                return 200 <= resp.status_code < 300
        except httpx.HTTPError:
            return False
