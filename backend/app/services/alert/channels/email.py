"""邮件渠道：SMTP（smtplib 为阻塞实现，走线程池）。"""

from __future__ import annotations

import asyncio
import smtplib
from email.mime.text import MIMEText

from app.services.alert.channels.base import BaseChannel


class EmailChannel(BaseChannel):
    type = "email"

    def required_fields(self) -> list[str]:
        return ["host", "port", "username", "password", "to"]

    async def send(self, config: dict, title: str, body: str) -> bool:
        def _send() -> bool:
            # 规则名虽已在 schema 禁 CRLF，此处双保险：头注入（CWE-93）直通 SMTP
            safe_title = " ".join(str(title).split())
            msg = MIMEText(f"[nasdeck] {safe_title}\n{body}", "plain", "utf-8")
            msg["Subject"] = f"[nasdeck] {safe_title}"
            msg["From"] = config.get("from") or config["username"]
            msg["To"] = config["to"]
            try:
                with smtplib.SMTP(config["host"], int(config["port"]), timeout=15) as smtp:
                    if config.get("tls", True):
                        smtp.starttls()
                    smtp.login(config["username"], config["password"])
                    smtp.sendmail(msg["From"], [config["to"]], msg.as_string())
                return True
            except (smtplib.SMTPException, OSError):
                return False

        return await asyncio.to_thread(_send)
