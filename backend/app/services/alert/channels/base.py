"""通知渠道基类与注册表（契约 §2.19/§3.5：新类型追加 CHANNEL_TYPES 白名单）。"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

from app.core.exceptions import InvalidParamsError

CHANNEL_TYPES = ("telegram", "bark", "email", "webhook")


# URL 内嵌凭据：userinfo（scheme://user:pass@host）与查询串里的 token/key 参数
_URL_USERINFO_RE = re.compile(r"((?:https?|ftps?)://)([^@/\s:]+):([^@/\s]+)@")
_URL_QUERY_SECRET_RE = re.compile(
    r"([?&](?:[a-z_]*(?:token|key|secret|password|sig|signature)[a-z_]*=))([^&#\s]+)", re.IGNORECASE
)


def _mask_url(text: str) -> str:
    text = _URL_USERINFO_RE.sub(r"\1\2:****@", text)
    return _URL_QUERY_SECRET_RE.sub(r"\1****", text)


def mask_config(channel_type: str, config: dict) -> dict:
    """读接口脱敏：token/密码/邮箱打码；URL 值打掉内嵌凭据（webhook url 常带
    user:pass@ 或 ?token=，此前原样暴露给所有可读接口的登录用户）。"""
    masked = {}
    for key, value in config.items():
        text = str(value)
        if any(k in key.lower() for k in ("token", "key", "password", "secret")):
            masked[key] = text[:4] + "****" if len(text) > 4 else "****"
        elif "@" in text and channel_type == "email":
            masked[key] = re.sub(r"^(\S)@.*$", r"\1***", text)
        elif "://" in text:
            masked[key] = _mask_url(text)
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
