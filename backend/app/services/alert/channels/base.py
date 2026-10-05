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
    """打掉 URL 中内嵌凭据（userinfo 与查询串里的 token/key 等参数）。

    Args:
        text (str): 原始 URL 文本。

    Returns:
        str: 凭据替换为 **** 后的 URL。
    """
    text = _URL_USERINFO_RE.sub(r"\1\2:****@", text)
    return _URL_QUERY_SECRET_RE.sub(r"\1****", text)


def mask_config(channel_type: str, config: dict) -> dict:
    """读接口脱敏：token/密码/邮箱打码；URL 值打掉内嵌凭据。

    webhook url 常带 user:pass@ 或 ?token=，此前原样暴露给所有可读
    接口的登录用户（审查记录）。

    Args:
        channel_type (str): 渠道类型（email 时对含 @ 的值做邮箱打码）。
        config (dict): 原始渠道配置。

    Returns:
        dict: 脱敏后的配置副本（键名不变）。
    """
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
    """通知渠道抽象基类：子类声明 type 与 required_fields，实现 send。

    Attributes:
        type (str): 渠道类型标识（与 CHANNEL_TYPES 白名单一致）。
    """

    type: str = "base"

    @abstractmethod
    async def send(self, config: dict, title: str, body: str) -> bool:
        """发送一条通知（不抛异常，失败以返回值表达）。

        Args:
            config (dict): 渠道配置，各键含义见子类 required_fields/docstring。
            title (str): 通知标题。
            body (str): 通知正文。

        Returns:
            bool: 成功 True / 失败 False。
        """

    def validate(self, config: dict) -> None:
        """校验渠道配置必填字段齐全。

        Args:
            config (dict): 渠道配置。

        Raises:
            InvalidParamsError: required_fields 中存在缺失或为空的字段。
        """
        required = self.required_fields()
        missing = [f for f in required if not config.get(f)]
        if missing:
            raise InvalidParamsError(f"{self.type} 渠道缺少字段: {', '.join(missing)}")

    @abstractmethod
    def required_fields(self) -> list[str]:
        """子类声明 send 所需的 config 必填键。

        Returns:
            list[str]: 必填字段名列表（validate 逐项检查）。
        """
        ...
