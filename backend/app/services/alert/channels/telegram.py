"""Telegram 渠道：Bot API sendMessage。"""

from __future__ import annotations

import httpx

from app.services.alert.channels.base import BaseChannel


class TelegramChannel(BaseChannel):
    """Telegram Bot 渠道：sendMessage API（bot_token + chat_id）。"""

    type = "telegram"

    def required_fields(self) -> list[str]:
        """send 所需的 config 必填键。

        Returns:
            list[str]: ["bot_token", "chat_id"]。
        """
        return ["bot_token", "chat_id"]

    async def send(self, config: dict, title: str, body: str) -> bool:
        """调 Bot API sendMessage 推送一条通知（10s 超时）。

        Args:
            config (dict): 渠道配置。bot_token：Bot 令牌（必填）；
                chat_id：目标会话 id（必填）。
            title (str): 通知标题（与正文合并发送，加 [nasdeck] 前缀）。
            body (str): 通知正文。

        Returns:
            bool: HTTP 200 即 True；网络异常 False。
        """
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"https://api.telegram.org/bot{config['bot_token']}/sendMessage",
                    json={"chat_id": config["chat_id"], "text": f"[nasdeck] {title}\n{body}"},
                )
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
