"""
Authentication and registration endpoints
"""

import asyncio
import hashlib
import re
import secrets
import string
from typing import Optional
from urllib.parse import urlencode, urlsplit, urlunsplit
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pub.contract.auth import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    PasswordSetupRequest,
    RegisterRequest,
    RegisterResponse,
)
from pub.models.customer import Account
from pub.services import AuthService, get_session
from pub.utils.jwt_token import (
    create_access_token,
    create_password_setup_token,
    decode_access_token,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.email import EmailDeliveryError, send_registration_email
from app.config import settings
from app.utils.auth import get_current_account
from app.utils.response import success

router = APIRouter(tags=["auth"])

USERNAME_FLAG_EMAIL = 1
PASSWORD_SETUP_PREFIX = "!setup:"


def _company_slug(company_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", company_name.lower()).strip("-")
    return slug or "tenant"


def _normalize_phone(phone: str) -> str:
    return re.sub(r"\D", "", phone)


def _password_setup_marker(nonce: str) -> str:
    digest = hashlib.sha256(nonce.encode("utf-8")).hexdigest()
    return f"{PASSWORD_SETUP_PREFIX}{digest}"


def _build_password_setup_url(token: str) -> str:
    portal = urlsplit(settings.portal_login_url)
    query = urlencode({"token": token})
    return urlunsplit((portal.scheme, portal.netloc, "/set-password", query, ""))


async def _generate_unique_tenant_code(session: AsyncSession) -> str:
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(8):
        code = "".join(secrets.choice(alphabet) for _ in range(8))
        existing = await AuthService.get_tenant_by_code(session, code)
        if existing is None:
            return code
    raise HTTPException(status_code=500, detail="Unable to generate unique tenant code")


@router.post("/auth/register")
async def register(
    payload: RegisterRequest,
    session: AsyncSession = Depends(get_session),
):
    normalized_phone = _normalize_phone(payload.phone)
    if not normalized_phone:
        raise HTTPException(status_code=400, detail="phone must include numbers")

    username = payload.email
    login_channel = "email"
    account_flag = USERNAME_FLAG_EMAIL

    tenant_code = await _generate_unique_tenant_code(session)
    tenant_mqtt_server = f"mqtt.{_company_slug(payload.company_name)}.portal.local"
    tenant_api_server = f"api.{_company_slug(payload.company_name)}.portal.local"
    setup_nonce = secrets.token_urlsafe(32)
    password_marker = _password_setup_marker(setup_nonce)

    try:
        result = await AuthService.register(
            session=session,
            username=username,
            email=payload.email,
            normalized_phone=normalized_phone,
            company_name=payload.company_name,
            contact_name=payload.contact_name,
            login_channel=login_channel,
            account_flag=account_flag,
            tenant_code=tenant_code,
            tenant_mqtt_server=tenant_mqtt_server,
            tenant_api_server=tenant_api_server,
            password_value=password_marker,
        )
        setup_token = create_password_setup_token(
            subject=str(result["account_id"]),
            nonce=setup_nonce,
            jwt_secret_key=settings.jwt_secret_key,
            expires_minutes=settings.password_setup_token_expires_minutes,
        )
        await asyncio.to_thread(
            send_registration_email,
            recipient=payload.email,
            contact_name=payload.contact_name,
            company_name=payload.company_name,
            password_setup_url=_build_password_setup_url(setup_token),
        )
        await AuthService.commit(session)
    except EmailDeliveryError as exc:
        await AuthService.rollback(session)
        raise HTTPException(
            status_code=503,
            detail="registration email could not be sent; no account was created",
        ) from exc
    except Exception:
        await AuthService.rollback(session)
        raise

    return success(RegisterResponse(
        tenant_id=result["tenant_id"],
        contact_id=result["contact_id"],
        account_id=result["account_id"],
        account_username=result["account_username"],
        login_channel=result["login_channel"],
        email_sent=True,
    ))


@router.post("/auth/set-password")
async def set_initial_password(
    payload: PasswordSetupRequest,
    session: AsyncSession = Depends(get_session),
):
    try:
        token_payload = decode_access_token(payload.token, settings.jwt_secret_key)
        if token_payload.get("purpose") != "password_setup":
            raise ValueError("invalid token purpose")
        account_id = UUID(str(token_payload.get("sub")))
        nonce = token_payload.get("nonce")
        if not isinstance(nonce, str) or not nonce:
            raise ValueError("invalid token nonce")
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail="password setup link is invalid or expired",
        ) from exc

    consumed = await AuthService.consume_password_setup(
        session,
        account_id,
        _password_setup_marker(nonce),
        payload.new_password,
    )
    if not consumed:
        raise HTTPException(
            status_code=400,
            detail="password setup link is invalid, expired, or already used",
        )

    return success({"message": "password set successfully"})


@router.post("/auth/login")
async def login(
    payload: LoginRequest,
    session: AsyncSession = Depends(get_session),
):
    account = await AuthService.get_account_by_credentials(
        session, payload.username, payload.password
    )
    if account is None:
        raise HTTPException(status_code=401, detail="invalid username or password")

    tenant_name: Optional[str] = None
    contact_name: Optional[str] = None

    tenant = await AuthService.get_tenant_by_id(session, account.tenant_id)  # type: ignore[arg-type]
    if tenant is not None:
        tenant_name = str(tenant.name)

    if account.contact_id:  # type: ignore[truthy-bool]
        contact = await AuthService.get_contact_by_id(session, account.contact_id)  # type: ignore[arg-type]

        if contact is not None:
            contact_name = str(contact.name)

    expires_in = settings.jwt_access_token_expires_minutes * 60
    access_token = create_access_token(
        subject=str(account.id),
        tenant_id=str(account.tenant_id),
        username=account.username,  # type: ignore[arg-type]
        jwt_secret_key=settings.jwt_secret_key,
        admin=account.admin,  # type: ignore[arg-type]
        contact_id=str(account.contact_id) if account.contact_id else None,  # type: ignore[truthy-bool]
        flag=account.flag,  # type: ignore[arg-type]
        expires_minutes=settings.jwt_access_token_expires_minutes,
    )

    return success(LoginResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=expires_in,
        account_id=account.id,  # type: ignore[arg-type]
        username=account.username,  # type: ignore[arg-type]
        tenant_id=account.tenant_id,  # type: ignore[arg-type]
        tenant_name=tenant_name,
        contact_id=account.contact_id,  # type: ignore[arg-type]
        contact_name=contact_name,
        flag=account.flag,  # type: ignore[arg-type]
    ))


@router.post("/auth/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    current_account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    # Because JWT is stateless, we must query DB for the real password hash
    db_account = await AuthService.get_account(session, current_account.id)  # type: ignore[arg-type]
    if not db_account or db_account.password != payload.current_password:  # type: ignore[truthy-bool]
        raise HTTPException(status_code=400, detail="current password is incorrect")

    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="new password must be different")

    await AuthService.update_account_password(session, db_account, payload.new_password)
    return success({"message": "password updated"})
