"""邮件渠道：SMTP（smtplib 为阻塞实现，走线程池）。"""

from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from email.mime.text import MIMEText

from app.core.exceptions import InvalidParamsError
from app.services.alert.channels.base import BaseChannel
from app.utils.net_guard import assert_public_host

logger = logging.getLogger(__name__)


class EmailChannel(BaseChannel):
    type = "email"

    def required_fields(self) -> list[str]:
        return ["host", "port", "username", "password", "to"]

    def validate(self, config: dict) -> None:
        super().validate(config)
        # SSRF 护栏：SMTP host 不得指向内网（root 运行 + /test 即时反馈 = 端口扫描面）
        assert_public_host(config["host"], config["port"], what="SMTP host")

    async def send(self, config: dict, title: str, body: str) -> str | None:
        def _clean_header(value: str) -> str:
            # To/From 同 title 一样禁 CRLF：头注入（CWE-93）直通 SMTP（原型 C3）
            return " ".join(str(value).split())

        def _send() -> str | None:
            safe_title = _clean_header(title)
            msg = MIMEText(f"[nasdeck] {safe_title}\n{body}", "plain", "utf-8")
            msg["Subject"] = f"[nasdeck] {safe_title}"
            msg["From"] = _clean_header(config.get("from") or config["username"])
            msg["To"] = _clean_header(config["to"])
            try:
                with smtplib.SMTP(config["host"], int(config["port"]), timeout=15) as smtp:
                    if config.get("tls", True):
                        # 默认 context 会校验证书：不传时 smtplib 不校验，内网 MITM 可截登录凭据
                        smtp.starttls(ssl.create_default_context())
                    smtp.login(config["username"], config["password"])
                    smtp.sendmail(msg["From"], [config["to"]], msg.as_string())
                return None
            except smtplib.SMTPAuthenticationError:
                return "auth_failed"
            except smtplib.SMTPException:
                return "bad_response"
            except (OSError, ValueError):
                return "network"

        try:
            # 发送时复检：防保存后 DNS 被改指向内网；port 非数字也在此拦截（不逃异常契约）
            assert_public_host(config["host"], config["port"], what="SMTP host")
        except InvalidParamsError as exc:
            logger.warning("email 发送被 SSRF 护栏拒绝: %s", exc)
            return "ssrf_rejected"
        return await asyncio.to_thread(_send)
