"""敏感信息脱敏引擎：IP / 序列号 / MAC / 路径 / 邮箱 / IPv6 / 密钥值打码（报告与诊断包用）。"""

from __future__ import annotations

import re

_PATTERNS = [
    (re.compile(r"\b(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\b"), r"\1.\2.*.*"),
    # 完整 IPv6（含 :: 缩写简化形态，8 组以内 hex 段）
    (re.compile(r"\b(?:[0-9A-Fa-f]{1,4}:){2,7}[0-9A-Fa-f]{1,4}\b"), "XXXX:XXXX:…"),
    # MAC 三种形态：冒号 / 连字符（ip、ifconfig 常见）/ 点分（Windows、部分驱动日志）
    (re.compile(r"\b([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b"), "XX:XX:XX:XX:XX:XX"),
    (re.compile(r"\b([0-9A-Fa-f]{2}-){5}[0-9A-Fa-f]{2}\b"), "XX-XX-XX-XX-XX-XX"),
    (re.compile(r"\b([0-9A-Fa-f]{4}\.){2}[0-9A-Fa-f]{4}\b"), "XXXX.XXXX.XXXX"),
    # 序列号：S/N、SN、serial、serial number，前缀分隔符 [:=>] 或空白均可；
    # 值要求含至少一位数字，避免把 "S/N healthy" 这类普通词误杀
    (
        re.compile(r"(?i:\b(s/?n|serial(?:\s*number)?))\s*[:=]?\s*(?=[A-Z0-9-]*\d)[A-Z0-9-]{6,}"),
        r"\1********",
    ),
    # 设备/挂载路径：盘符、挂载点、用户目录（序列号之外最常见的身份指纹）
    (re.compile(r"(?<![\w])/(dev|mnt|media|home|vol(?:ume)?\d*|run|var/apps)/[^\s\"'<>]+"), r"/\1/***"),
    (re.compile(r"\b([A-Za-z0-9._%+-])[@][A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), r"\1***@***"),
]

# key 命中即整值打码：SystemSetting 是自由 KV，用户可能存任何 token/password 类值，
# 诊断包分享即泄露（value 级正则覆盖不了任意凭据形态）
_SECRET_KEY_RE = re.compile(r"token|secret|password|passwd|credential|api[_-]?key", re.IGNORECASE)


def desensitize(text: str, enabled: bool = True) -> str:
    if not enabled:
        return text
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text


def mask_secret_values(mapping: dict, enabled: bool = True) -> dict:
    """按 key 命中递归打码整个值（settings dump 用）：key 含 token/secret/password 等
    即视为凭据，整个子树打码；嵌套 dict/list 继续按同规则下钻——顶层 key 无害
    不代表嵌套结构里没有凭据（评审 2026-10-25 P0-C：嵌套 config 曾原样保留）。"""
    if not enabled:
        return dict(mapping)
    return _mask_mapping(mapping)


def _mask_mapping(mapping: dict) -> dict:
    out = {}
    for key, value in mapping.items():
        if _SECRET_KEY_RE.search(str(key)) and value not in (None, ""):
            out[key] = "********"
        else:
            out[key] = _mask_item(value)
    return out


def _mask_item(value: object) -> object:
    if isinstance(value, dict):
        return _mask_mapping(value)
    if isinstance(value, list):
        return [_mask_item(v) for v in value]
    return value
