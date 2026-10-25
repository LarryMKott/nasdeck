"""出网地址护栏：用户可配的告警 URL/主机不得指向内网/回环/云元数据（SSRF 防护）。

面板以 root 运行（fpk/config/privilege），webhook/bark 的 server、email 的 SMTP
host 都是用户可配字段；不加护栏时它们等于给登录用户一个内网探测原语，
`POST /alert/channels/{id}/test` 还提供即时布尔反馈，探测成本极低。

防线设计（评审 2026-10-25 P0-B）：
- 保存时（validate）与发送时（send）双重校验，防保存后 DNS 记录被改为内网指向；
- 解析主机名的全部 A/AAAA 记录逐一检查，任一命中禁段即拒绝；
- 残余 TOCTOU 窗口（我校验后 httpx 再解析一次）对本威胁模型可接受：护栏目标是
  封死内网/元数据目标，而非抵御控制 DNS+TLS 基础设施的对抗者。
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

from app.core.exceptions import InvalidParamsError

# 100.64.0.0/10（CGNAT）：ipaddress 的 is_private 不含该段，云内网常见，一并拒绝
_CGNAT = ipaddress.ip_network("100.64.0.0/10")


def _ip_forbidden(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local  # 含 169.254.169.254 云元数据
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
        or (ip.version == 4 and ip in _CGNAT)
    )


def _resolve_all(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """解析主机全部地址（字面量 IP 不走 DNS）。测试以 monkeypatch 本函数保持离线。"""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise InvalidParamsError(f"无法解析主机 {host}: {exc}") from exc
    return [ipaddress.ip_address(info[4][0]) for info in infos]


def assert_public_url(url: str, *, what: str = "url") -> None:
    """http(s) URL 出网校验：scheme 白名单 + 解析后全部 IP 不在禁段。"""
    parsed = urlsplit(str(url))
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise InvalidParamsError(f"{what} 须为 http(s) 地址")
    for ip in _resolve_all(parsed.hostname):
        if _ip_forbidden(ip):
            raise InvalidParamsError(f"{what} 指向内网/保留地址（{ip}），不允许")


def assert_public_host(host: str, port: int | str, *, what: str = "host") -> None:
    """SMTP 等裸 host:port 的出网校验。"""
    host = str(host).strip()
    if not host:
        raise InvalidParamsError(f"{what} 不能为空")
    try:
        int(port)
    except (TypeError, ValueError) as exc:
        raise InvalidParamsError(f"{what} 端口须为数字") from exc
    for ip in _resolve_all(host):
        if _ip_forbidden(ip):
            raise InvalidParamsError(f"{what} 指向内网/保留地址（{ip}），不允许")
