"""
Authentication and registration endpoints
"""

import re
import secrets
import string
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.contract.common import ApiResponse
from app.services.dependencies import get_session
from app.models.customer import Account
from app.services.customer_service import AuthService
from app.utils.auth import get_current_account
from app.utils.jwt_token import create_access_token
from app.utils.response import success
from app.contract.auth import (
    RegisterRequest,
    RegisterResponse,
    LoginRequest,
    LoginResponse,
    ChangePasswordRequest,
)

router = APIRouter(tags=["auth"])

USERNAME_FLAG_EMAIL = 1
USERNAME_FLAG_MOBILE = 2


def _company_slug(company_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", company_name.lower()).strip("-")
    return slug or "tenant"


def _normalize_phone(phone: str) -> str:
    return re.sub(r"\D", "", phone)


def _generate_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


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

    username = payload.email or normalized_phone
    login_channel = "email" if payload.email else "mobile"
    account_flag = USERNAME_FLAG_EMAIL if payload.email else USERNAME_FLAG_MOBILE

    tenant_code = await _generate_unique_tenant_code(session)
    tenant_host = f"{_company_slug(payload.company_name)}.portal.local"
    random_password = _generate_password()

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
            tenant_host=tenant_host,
            random_password=random_password,
        )
        await AuthService.commit(session)
    except Exception:
        await AuthService.rollback(session)
        raise

    return success(RegisterResponse(
        tenant_id=result["tenant_id"],
        contact_id=result["contact_id"],
        account_id=result["account_id"],
        account_username=result["account_username"],
        login_channel=result["login_channel"],
        generated_password=result["generated_password"],
    ))


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

    tenant = await AuthService.get_tenant_by_id(session, account.tenant_id)
    if tenant is not None:
        tenant_name = tenant.name

    if account.contact_id:
        contact = await AuthService.get_contact_by_id(session, account.contact_id)
        if contact is not None:
            contact_name = contact.name

    expires_in = settings.jwt_access_token_expires_minutes * 60
    access_token = create_access_token(
        subject=str(account.id),
        tenant_id=str(account.tenant_id),
        username=account.username,
    )

    return success(LoginResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=expires_in,
        account_id=account.id,
        username=account.username,
        tenant_id=account.tenant_id,
        tenant_name=tenant_name,
        contact_id=account.contact_id,
        contact_name=contact_name,
        flag=account.flag,
    ))


@router.post("/auth/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    current_account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    if current_account.password != payload.current_password:
        raise HTTPException(status_code=400, detail="current password is incorrect")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="new password must be different")

    await AuthService.update_account_password(session, current_account, payload.new_password)
    return success({"message": "password updated"})
