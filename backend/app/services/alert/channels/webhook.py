"""Webhook 渠道：POST JSON 到自定义 URL（契约 §2.19/§3.5）。"""

from __future__ import annotations

import httpx

from app.core.exceptions import InvalidParamsError
from app.services.alert.channels.base import BaseChannel


class WebhookChannel(BaseChannel):
    """Webhook 渠道：JSON POST {source, title, body}，2xx 即成功。"""

    type = "webhook"

    def required_fields(self) -> list[str]:
        """send 所需的 config 必填键。

        Returns:
            list[str]: ["url"]。
        """
        return ["url"]

    def validate(self, config: dict) -> None:
        """校验 url 必填且须为 http(s) 地址。

        Args:
            config (dict): 渠道配置。

        Raises:
            InvalidParamsError: url 缺失，或非 http://、https:// 前缀。
        """
        super().validate(config)
        if not str(config["url"]).startswith(("http://", "https://")):
            raise InvalidParamsError("webhook url 须为 http(s) 地址")

    async def send(self, config: dict, title: str, body: str) -> bool:
        """POST JSON 到自定义 URL（10s 超时，2xx 视为成功）。

        Args:
            config (dict): 渠道配置。url：http(s) 目标地址（必填）。
            title (str): 通知标题（JSON title 键）。
            body (str): 通知正文（JSON body 键）。

        Returns:
            bool: 状态码 2xx 即 True；网络异常 False。
        """
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    config["url"],
                    json={"source": "nasdeck", "title": title, "body": body},
                )
                return 200 <= resp.status_code < 300
        except httpx.HTTPError:
            return False
