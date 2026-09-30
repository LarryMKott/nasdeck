"""通知渠道基类与注册表（契约 §2.19/§3.5：新类型追加 CHANNEL_TYPES 白名单）。"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

from app.core.exceptions import InvalidParamsError

CHANNEL_TYPES = ("telegram", "bark", "email", "webhook")


def mask_config(channel_type: str, config: dict) -> dict:
    """读接口脱敏：token/密码/邮箱打码。"""
    masked = {}
    for key, value in config.items():
        text = str(value)
        if any(k in key.lower() for k in ("token", "key", "password", "secret")):
            masked[key] = text[:4] + "****" if len(text) > 4 else "****"
        elif "@" in text and channel_type == "email":
            masked[key] = re.sub(r"^(\S)@.*$", r"\1***", text)
        else:
            masked[key] = value
    return masked


class BaseChannel(ABC):
    type: str = "base"

    @abstractmethod
    async def send(self, config: dict, title: str, body: str) -> bool:
        """发送通知，成功 True / 失败 False（不抛异常）。"""

    def validate(self, config: dict) -> None:
        required = self.required_fields()
        missing = [f for f in required if not config.get(f)]
        if missing:
            raise InvalidParamsError(f"{self.type} 渠道缺少字段: {', '.join(missing)}")

    @abstractmethod
    def required_fields(self) -> list[str]: ...
