from unittest.mock import Mock

import pytest

from app.clients import email as email_client


def _configure_email(monkeypatch):
    monkeypatch.setattr(email_client.settings, "email_server", "mail.langhu.ai")
    monkeypatch.setattr(email_client.settings, "email_port", 587)
    monkeypatch.setattr(email_client.settings, "email_use_tls", True)
    monkeypatch.setattr(email_client.settings, "email_tls_verify", True)
    monkeypatch.setattr(
        email_client.settings,
        "email_account",
        "platform@langhu.ai",
    )
    monkeypatch.setattr(email_client.settings, "email_passwd", "test-secret")


def test_registration_email_uses_mailcow_submission(monkeypatch):
    _configure_email(monkeypatch)
    smtp = Mock()
    smtp_context = Mock()
    smtp_context.__enter__ = Mock(return_value=smtp)
    smtp_context.__exit__ = Mock(return_value=False)
    smtp_factory = Mock(return_value=smtp_context)
    monkeypatch.setattr(email_client.smtplib, "SMTP", smtp_factory)

    email_client.send_registration_email(
        recipient="user@example.com",
        contact_name="测试用户",
        company_name="测试企业",
        password_setup_url="https://portal.api-server.icu/set-password?token=signed-token",
    )

    smtp_factory.assert_called_once_with("mail.langhu.ai", 587, timeout=15)
    smtp.starttls.assert_called_once()
    smtp.login.assert_called_once_with("platform@langhu.ai", "test-secret")
    sent_message = smtp.send_message.call_args.args[0]
    assert sent_message["To"] == "user@example.com"
    plain_body = sent_message.get_body(preferencelist=("plain",)).get_content()
    assert "临时密码" not in plain_body
    assert "https://portal.api-server.icu/set-password?token=signed-token" in plain_body
    assert "设置登录密码" in sent_message.get_body(
        preferencelist=("html",)
    ).get_content()


def test_registration_email_can_accept_mailcow_self_signed_certificate(monkeypatch):
    _configure_email(monkeypatch)
    monkeypatch.setattr(email_client.settings, "email_tls_verify", False)
    tls_context = Mock()
    monkeypatch.setattr(email_client.ssl, "create_default_context", Mock(return_value=tls_context))
    smtp = Mock()
    smtp_context = Mock()
    smtp_context.__enter__ = Mock(return_value=smtp)
    smtp_context.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(email_client.smtplib, "SMTP", Mock(return_value=smtp_context))

    email_client.send_registration_email(
        recipient="user@example.com",
        contact_name="测试用户",
        company_name="测试企业",
        password_setup_url="https://portal.api-server.icu/set-password?token=signed-token",
    )

    assert tls_context.check_hostname is False
    assert tls_context.verify_mode == email_client.ssl.CERT_NONE
    smtp.starttls.assert_called_once_with(context=tls_context)


def test_registration_email_requires_configuration(monkeypatch):
    monkeypatch.setattr(email_client.settings, "email_server", "")

    with pytest.raises(
        email_client.EmailDeliveryError,
        match="not configured",
    ):
        email_client.send_registration_email(
            recipient="user@example.com",
            contact_name="测试用户",
            company_name="测试企业",
            password_setup_url="https://portal.api-server.icu/set-password?token=signed-token",
        )
