"""SMTP client for registration emails sent through Mailcow."""

import logging
import smtplib
import ssl
from email.message import EmailMessage
from html import escape

from app.config import settings

logger = logging.getLogger(__name__)


class EmailDeliveryError(RuntimeError):
    """Raised when a registration email cannot be accepted by the SMTP server."""


def send_registration_email(
    *,
    recipient: str,
    contact_name: str,
    company_name: str,
    password_setup_url: str,
) -> None:
    if not settings.email_server or not settings.email_account or not settings.email_passwd:
        raise EmailDeliveryError("registration email is not configured")

    message = EmailMessage()
    message["Subject"] = "朗湖智能平台账号注册成功"
    message["From"] = settings.email_account
    message["To"] = recipient
    message.set_content(
        "\n".join(
            [
                f"{contact_name}，您好：",
                "",
                f"{company_name} 的朗湖智能平台账号已创建。",
                f"登录账号：{recipient}",
                f"设置密码：{password_setup_url}",
                "",
                "请在 24 小时内打开链接并设置登录密码。该链接仅可使用一次。",
                "如果这不是您的操作，请忽略此邮件并联系我们。",
            ]
        )
    )
    message.add_alternative(
        f"""
        <html>
          <body style="font-family:Arial,sans-serif;color:#111827;line-height:1.6">
            <p>{escape(contact_name)}，您好：</p>
            <p><strong>{escape(company_name)}</strong> 的朗湖智能平台账号已创建。</p>
            <table style="border-collapse:collapse">
              <tr>
                <td style="padding:6px 12px 6px 0">登录账号</td>
                <td><strong>{escape(recipient)}</strong></td>
              </tr>
            </table>
            <p><a href="{escape(password_setup_url, quote=True)}">设置登录密码</a></p>
            <p>请在 24 小时内打开链接并设置登录密码。该链接仅可使用一次。</p>
            <p style="color:#6b7280">如果这不是您的操作，请忽略此邮件并联系我们。</p>
          </body>
        </html>
        """,
        subtype="html",
    )

    try:
        with smtplib.SMTP(
            settings.email_server,
            settings.email_port,
            timeout=15,
        ) as smtp:
            smtp.ehlo()
            if settings.email_use_tls:
                tls_context = ssl.create_default_context()
                if not settings.email_tls_verify:
                    tls_context.check_hostname = False
                    tls_context.verify_mode = ssl.CERT_NONE
                smtp.starttls(context=tls_context)
                smtp.ehlo()
            smtp.login(settings.email_account, settings.email_passwd)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        logger.warning(
            "Registration email failed via %s:%d: %s: %s",
            settings.email_server,
            settings.email_port,
            type(exc).__name__,
            exc,
        )
        raise EmailDeliveryError("registration email delivery failed") from exc
