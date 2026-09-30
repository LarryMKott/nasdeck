"""敏感信息脱敏引擎：IP / 序列号 / MAC / 邮箱打码（报告与诊断包用）。"""

from __future__ import annotations

import re

_PATTERNS = [
    (re.compile(r"\b(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\b"), r"\1.\2.*.*"),
    (re.compile(r"\b([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b"), "XX:XX:XX:XX:XX:XX"),
    (re.compile(r"\b(S/N[:\s]*)[A-Z0-9]+", re.IGNORECASE), r"\1********"),
    (re.compile(r"\b([A-Za-z0-9._%+-])[@][A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), r"\1***@***"),
]


def desensitize(text: str, enabled: bool = True) -> str:
    if not enabled:
        return text
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text
