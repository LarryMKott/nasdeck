"""Telegram 渠道：Bot API sendMessage。"""

from __future__ import annotations

import httpx

from app.services.alert.channels.base import BaseChannel


class TelegramChannel(BaseChannel):
    type = "telegram"

    def required_fields(self) -> list[str]:
        return ["bot_token", "chat_id"]

    async def send(self, config: dict, title: str, body: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"https://api.telegram.org/bot{config['bot_token']}/sendMessage",
                    json={"chat_id": config["chat_id"], "text": f"[nasdeck] {title}\n{body}"},
                )
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
