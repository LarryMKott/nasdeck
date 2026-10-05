"""Bark 渠道：iOS 推送（GET/{server}/{key}/{title}/{body}）。"""

from __future__ import annotations

from urllib.parse import quote

import httpx

from app.services.alert.channels.base import BaseChannel


class BarkChannel(BaseChannel):
    """Bark (iOS) 推送渠道：GET https://api.day.app/<key>/<title>/<body>。"""

    type = "bark"

    def required_fields(self) -> list[str]:
        """send 所需的 config 必填键。

        Returns:
            list[str]: ["device_key"]。
        """
        return ["device_key"]

    async def send(self, config: dict, title: str, body: str) -> bool:
        """GET 请求 Bark 服务器推送一条通知（10s 超时）。

        Args:
            config (dict): 渠道配置。device_key：Bark 设备推送 key（必填）；
                server：自建 Bark 服务器地址，缺省 https://api.day.app。
            title (str): 通知标题（路径段全编码）。
            body (str): 通知正文（路径段全编码）。

        Returns:
            bool: HTTP 200 即 True；网络异常 False。
        """
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
