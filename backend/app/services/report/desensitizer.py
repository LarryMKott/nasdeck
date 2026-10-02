"""敏感信息脱敏引擎：IP / 序列号 / MAC / 邮箱 / IPv6 / 密钥值打码（报告与诊断包用）。"""

from __future__ import annotations

import re

_PATTERNS = [
    (re.compile(r"\b(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\b"), r"\1.\2.*.*"),
    # 完整 IPv6（含 :: 缩写简化形态，8 组以内 hex 段）
    (re.compile(r"\b(?:[0-9A-Fa-f]{1,4}:){2,7}[0-9A-Fa-f]{1,4}\b"), "XXXX:XXXX:…"),
    (re.compile(r"\b([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b"), "XX:XX:XX:XX:XX:XX"),
    (re.compile(r"\b(S/N[:\s]*)[A-Z0-9]+", re.IGNORECASE), r"\1********"),
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
    """按 key 命中打码整个值（settings dump 用）：key 含 token/secret/password 等
    即视为凭据。仅处理顶层标量值，嵌套结构原样保留（正则兜底仍生效）。"""
    if not enabled:
        return dict(mapping)
    out = {}
    for key, value in mapping.items():
        if _SECRET_KEY_RE.search(str(key)) and isinstance(value, str) and value:
            out[key] = "********"
        else:
            out[key] = value
    return out
