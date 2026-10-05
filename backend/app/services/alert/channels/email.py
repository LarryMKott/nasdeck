"""邮件渠道：SMTP（smtplib 为阻塞实现，走线程池）。"""

from __future__ import annotations

import asyncio
import smtplib
from email.mime.text import MIMEText

from app.services.alert.channels.base import BaseChannel


class EmailChannel(BaseChannel):
    """邮件 SMTP 渠道：smtplib 明文/STARTTLS/TLS 可选，15s 超时。"""

    type = "email"

    def required_fields(self) -> list[str]:
        """send 所需的 config 必填键。

        Returns:
            list[str]: ["host", "port", "username", "password", "to"]。
        """
        return ["host", "port", "username", "password", "to"]

    async def send(self, config: dict, title: str, body: str) -> bool:
        """经 SMTP 发送纯文本邮件（阻塞实现走线程池，15s 超时）。

        Args:
            config (dict): 渠道配置。host/port：SMTP 服务器地址与端口（必填）；
                username/password：登录账号（必填）；to：收件地址（必填）；
                from：发件地址，缺省用 username；tls：是否 STARTTLS，缺省 True。
            title (str): 通知标题（Subject，加 [nasdeck] 前缀并清洗 CRLF）。
            body (str): 通知正文。

        Returns:
            bool: 发送成功 True；SMTP/网络异常 False。
        """
        def _send() -> bool:
            """同步 SMTP 发信主体（运行于 wait_for 包装内，受 15s 超时约束）。"""
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
