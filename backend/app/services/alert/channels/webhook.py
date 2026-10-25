"""Webhook 渠道：POST JSON 到自定义 URL（契约 §2.19/§3.5）。"""

from __future__ import annotations

import logging

import httpx

from app.core.exceptions import InvalidParamsError
from app.services.alert.channels.base import BaseChannel
from app.utils.net_guard import assert_public_url

logger = logging.getLogger(__name__)


class WebhookChannel(BaseChannel):
    type = "webhook"

    def required_fields(self) -> list[str]:
        return ["url"]

    def validate(self, config: dict) -> None:
        super().validate(config)
        # SSRF 护栏（评审 2026-10-25 P0-B）：scheme 白名单 + 内网/保留段拒绝
        assert_public_url(config["url"], what="webhook url")

    async def send(self, config: dict, title: str, body: str) -> str | None:
        try:
            # 发送时复检：防保存后 DNS 被改指向内网
            assert_public_url(config["url"], what="webhook url")
        except InvalidParamsError as exc:
            logger.warning("webhook 发送被 SSRF 护栏拒绝: %s", exc)
            return "ssrf_rejected"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    config["url"],
                    json={"source": "nasdeck", "title": title, "body": body},
                )
                if 200 <= resp.status_code < 300:
                    return None
                return "bad_response"
        except httpx.TimeoutException:
            return "timeout"
        except httpx.HTTPError:
            return "network"
