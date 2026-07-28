from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pub.contract.auth import PasswordSetupRequest, RegisterRequest
from pub.models import import_all_models
from pub.services.customer.auth_service import AuthService

from app.clients.email import EmailDeliveryError
from app.routers import auth as auth_router

import_all_models()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("lookup_name", "value"),
    [
        ("get_account_by_email", "tony.ju@163.com"),
        ("get_account_by_mobile", "18301880898"),
    ],
)
async def test_account_channel_lookup_uses_username(lookup_name, value):
    result = Mock()
    result.scalar_one_or_none.return_value = None
    session = Mock()
    session.execute = AsyncMock(return_value=result)

    await getattr(AuthService, lookup_name)(session, value)

    statement = session.execute.await_args.args[0]
    assert "account.username" in str(statement)


@pytest.mark.asyncio
async def test_register_keeps_email_and_mobile_on_contact_only(monkeypatch):
    tenant_id = uuid4()
    contact_id = uuid4()
    account_id = uuid4()
    captured = {}

    monkeypatch.setattr(
        AuthService,
        "get_account_by_username",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        AuthService,
        "get_account_by_email",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        AuthService,
        "get_contact_by_email",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        AuthService,
        "get_account_by_mobile",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        AuthService,
        "get_contact_by_mobile",
        AsyncMock(return_value=None),
    )

    async def create_tenant(_session, data):
        captured["tenant"] = data
        return SimpleNamespace(id=tenant_id)

    async def create_contact(_session, data):
        captured["contact"] = data
        return SimpleNamespace(id=contact_id)

    async def create_account(_session, data):
        captured["account"] = data
        return SimpleNamespace(id=account_id, username=data["username"])

    monkeypatch.setattr(AuthService, "create_tenant", create_tenant)
    monkeypatch.setattr(AuthService, "create_contact", create_contact)
    monkeypatch.setattr(AuthService, "create_account", create_account)

    result = await AuthService.register(
        session=Mock(),
        username="tony.ju@163.com",
        email="tony.ju@163.com",
        normalized_phone="18301880898",
        company_name="上海朗湖智能科技有限公司",
        contact_name="居向军",
        login_channel="email",
        account_flag=1,
        tenant_code="TENANT01",
        tenant_mqtt_server="mqtt.tenant.portal.local",
        tenant_api_server="api.tenant.portal.local",
        password_value="!setup:pending-marker",
    )

    assert captured["contact"]["email"] == "tony.ju@163.com"
    assert captured["contact"]["mobile"] == "18301880898"
    assert "email" not in captured["account"]
    assert "mobile" not in captured["account"]
    assert captured["account"]["username"] == "tony.ju@163.com"
    assert result["account_id"] == account_id
    assert "generated_password" not in result


def test_register_request_requires_email():
    with pytest.raises(ValueError):
        RegisterRequest(
            company_name="上海朗湖智能科技有限公司",
            contact_name="居向军",
            phone="18301880898",
        )


@pytest.mark.asyncio
async def test_create_tenant_does_not_commit_before_registration_finishes():
    session = Mock()
    session.add = Mock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    tenant = await AuthService.create_tenant(
        session,
        {
            "code": "TENANT01",
            "name": "上海朗湖智能科技有限公司",
            "mqtt_server": "mqtt.tenant.portal.local",
            "api_server": "api.tenant.portal.local",
            "active": True,
        },
    )

    session.add.assert_called_once_with(tenant)
    session.flush.assert_awaited_once()
    session.commit.assert_not_awaited()


def _registration_result():
    return {
        "tenant_id": uuid4(),
        "contact_id": uuid4(),
        "account_id": uuid4(),
        "account_username": "tony.ju@163.com",
        "login_channel": "email",
    }


@pytest.mark.asyncio
async def test_register_emails_one_time_password_setup_link(monkeypatch):
    result = _registration_result()
    monkeypatch.setattr(
        auth_router,
        "_generate_unique_tenant_code",
        AsyncMock(return_value="TENANT01"),
    )
    monkeypatch.setattr(auth_router.secrets, "token_urlsafe", lambda _length: "setup-nonce")
    monkeypatch.setattr(
        auth_router,
        "create_password_setup_token",
        Mock(return_value="signed-setup-token"),
    )
    monkeypatch.setattr(
        auth_router.AuthService,
        "register",
        AsyncMock(return_value=result),
    )
    send_email = Mock()
    monkeypatch.setattr(auth_router, "send_registration_email", send_email)
    session = Mock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    response = await auth_router.register(
        RegisterRequest(
            company_name="上海朗湖智能科技有限公司",
            contact_name="居向军",
            phone="18301880898",
            email="tony.ju@163.com",
        ),
        session,
    )

    send_email.assert_called_once_with(
        recipient="tony.ju@163.com",
        contact_name="居向军",
        company_name="上海朗湖智能科技有限公司",
        password_setup_url=(
            "https://portal.api-server.icu/set-password?token=signed-setup-token"
        ),
    )
    register_data = auth_router.AuthService.register.await_args.kwargs
    assert register_data["password_value"] == auth_router._password_setup_marker(
        "setup-nonce"
    )
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()
    assert response.data["email_sent"] is True
    assert "generated_password" not in response.data


@pytest.mark.asyncio
async def test_register_rolls_back_when_email_delivery_fails(monkeypatch):
    monkeypatch.setattr(
        auth_router,
        "_generate_unique_tenant_code",
        AsyncMock(return_value="TENANT01"),
    )
    monkeypatch.setattr(auth_router.secrets, "token_urlsafe", lambda _length: "setup-nonce")
    monkeypatch.setattr(
        auth_router,
        "create_password_setup_token",
        Mock(return_value="signed-setup-token"),
    )
    monkeypatch.setattr(
        auth_router.AuthService,
        "register",
        AsyncMock(return_value=_registration_result()),
    )
    monkeypatch.setattr(
        auth_router,
        "send_registration_email",
        Mock(side_effect=EmailDeliveryError("delivery failed")),
    )
    session = Mock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await auth_router.register(
            RegisterRequest(
                company_name="上海朗湖智能科技有限公司",
                contact_name="居向军",
                phone="18301880898",
                email="tony.ju@163.com",
            ),
            session,
        )

    assert exc_info.value.status_code == 503
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_password_setup_consumes_one_time_marker(monkeypatch):
    account_id = uuid4()
    token = auth_router.create_password_setup_token(
        subject=str(account_id),
        nonce="setup-nonce",
        jwt_secret_key=auth_router.settings.jwt_secret_key,
    )
    consume = AsyncMock(return_value=True)
    monkeypatch.setattr(auth_router.AuthService, "consume_password_setup", consume)
    session = Mock()

    response = await auth_router.set_initial_password(
        PasswordSetupRequest(token=token, new_password="new-password-123"),
        session,
    )

    consume.assert_awaited_once_with(
        session,
        account_id,
        auth_router._password_setup_marker("setup-nonce"),
        "new-password-123",
    )
    assert response.data["message"] == "password set successfully"


@pytest.mark.asyncio
async def test_password_setup_rejects_already_used_link(monkeypatch):
    account_id = uuid4()
    token = auth_router.create_password_setup_token(
        subject=str(account_id),
        nonce="setup-nonce",
        jwt_secret_key=auth_router.settings.jwt_secret_key,
    )
    monkeypatch.setattr(
        auth_router.AuthService,
        "consume_password_setup",
        AsyncMock(return_value=False),
    )

    with pytest.raises(HTTPException) as exc_info:
        await auth_router.set_initial_password(
            PasswordSetupRequest(token=token, new_password="new-password-123"),
            Mock(),
        )

    assert exc_info.value.status_code == 400
    assert "already used" in exc_info.value.detail


@pytest.mark.asyncio
async def test_password_setup_rejects_expired_link(monkeypatch):
    token = auth_router.create_password_setup_token(
        subject=str(uuid4()),
        nonce="setup-nonce",
        jwt_secret_key=auth_router.settings.jwt_secret_key,
        expires_minutes=-1,
    )
    consume = AsyncMock()
    monkeypatch.setattr(auth_router.AuthService, "consume_password_setup", consume)

    with pytest.raises(HTTPException) as exc_info:
        await auth_router.set_initial_password(
            PasswordSetupRequest(token=token, new_password="new-password-123"),
            Mock(),
        )

    assert exc_info.value.status_code == 400
    assert "expired" in exc_info.value.detail
    consume.assert_not_awaited()


@pytest.mark.asyncio
async def test_consume_password_setup_commits_matching_marker():
    result = Mock(rowcount=1)
    session = Mock()
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    consumed = await AuthService.consume_password_setup(
        session,
        uuid4(),
        "!setup:matching-marker",
        "new-password-123",
    )

    assert consumed is True
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_consume_password_setup_rolls_back_nonmatching_marker():
    result = Mock(rowcount=0)
    session = Mock()
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    consumed = await AuthService.consume_password_setup(
        session,
        uuid4(),
        "!setup:used-marker",
        "new-password-123",
    )

    assert consumed is False
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()
