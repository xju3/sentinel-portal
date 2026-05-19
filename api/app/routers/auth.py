"""
Authentication and registration endpoints
"""

import re
import secrets
import string
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import db_manager
from app.models.customer import Account, Contact, Tenant
from app.utils.auth import get_current_account
from app.utils.jwt_token import create_access_token

router = APIRouter(tags=["auth"])

USERNAME_FLAG_EMAIL = 1
USERNAME_FLAG_MOBILE = 2


class RegisterRequest(BaseModel):
    company_name: str
    contact_name: str
    phone: str
    email: Optional[str] = None

    @field_validator("company_name", "contact_name", "phone")
    @classmethod
    def validate_required_fields(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("field cannot be empty")
        return normalized

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip().lower()
        return normalized or None

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("invalid email format")
        return value


class RegisterResponse(BaseModel):
    tenant_id: UUID
    contact_id: UUID
    account_id: UUID
    account_username: str
    login_channel: str
    generated_password: str

    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    username: str
    password: str

    @field_validator("username", "password")
    @classmethod
    def validate_required_fields(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("field cannot be empty")
        return normalized


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    account_id: UUID
    username: str
    tenant_id: UUID
    tenant_name: Optional[str] = None
    contact_id: Optional[UUID] = None
    contact_name: Optional[str] = None
    flag: int

    model_config = ConfigDict(from_attributes=True)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("current_password", "new_password")
    @classmethod
    def validate_required_fields(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("field cannot be empty")
        return normalized


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
        result = await session.execute(select(Tenant).where(Tenant.code == code))
        if result.scalar_one_or_none() is None:
            return code
    raise HTTPException(status_code=500, detail="Unable to generate unique tenant code")


@router.post("/auth/register", response_model=RegisterResponse)
async def register(
    payload: RegisterRequest,
    session: AsyncSession = Depends(db_manager.get_session),
):
    normalized_phone = _normalize_phone(payload.phone)
    if not normalized_phone:
        raise HTTPException(status_code=400, detail="phone must include numbers")

    username = payload.email or normalized_phone
    login_channel = "email" if payload.email else "mobile"
    account_flag = USERNAME_FLAG_EMAIL if payload.email else USERNAME_FLAG_MOBILE

    existing_username = await session.execute(select(Account).where(Account.username == username))
    if existing_username.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="account username already exists")

    if payload.email:
        existing_email = await session.execute(select(Account).where(Account.email == payload.email))
        if existing_email.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="email already exists")
        existing_contact_email = await session.execute(
            select(Contact).where(Contact.email == payload.email)
        )
        if existing_contact_email.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="email already exists")

    existing_mobile = await session.execute(select(Account).where(Account.mobile == normalized_phone))
    if existing_mobile.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="phone already exists")
    existing_contact_mobile = await session.execute(
        select(Contact).where(Contact.mobile == normalized_phone)
    )
    if existing_contact_mobile.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="phone already exists")

    tenant_code = await _generate_unique_tenant_code(session)
    tenant_host = f"{_company_slug(payload.company_name)}.portal.local"
    random_password = _generate_password()

    try:
        tenant = Tenant(code=tenant_code, name=payload.company_name, host=tenant_host, active=True)
        session.add(tenant)
        await session.flush()

        contact = Contact(
            name=payload.contact_name,
            mobile=normalized_phone,
            email=payload.email,
            active=True,
            tenant_id=tenant.id,
        )
        session.add(contact)
        await session.flush()

        account = Account(
            username=username,
            password=random_password,
            email=payload.email,
            mobile=normalized_phone,
            flag=account_flag,
            active=True,
            contact_id=contact.id,
            tenant_id=tenant.id,
        )
        session.add(account)
        await session.flush()
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    return RegisterResponse(
        tenant_id=tenant.id,
        contact_id=contact.id,
        account_id=account.id,
        account_username=account.username,
        login_channel=login_channel,
        generated_password=random_password,
    )


@router.post("/auth/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    session: AsyncSession = Depends(db_manager.get_session),
):
    stmt = select(Account).where(
        Account.username == payload.username,
        Account.password == payload.password,
        Account.active == True,  # noqa: E712
    )
    result = await session.execute(stmt)
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=401, detail="invalid username or password")

    tenant_name: Optional[str] = None
    contact_name: Optional[str] = None

    tenant_result = await session.execute(select(Tenant).where(Tenant.id == account.tenant_id))
    tenant = tenant_result.scalar_one_or_none()
    if tenant is not None:
        tenant_name = tenant.name

    if account.contact_id:
        contact_result = await session.execute(select(Contact).where(Contact.id == account.contact_id))
        contact = contact_result.scalar_one_or_none()
        if contact is not None:
            contact_name = contact.name

    expires_in = settings.jwt_access_token_expires_minutes * 60
    access_token = create_access_token(
        subject=str(account.id),
        tenant_id=str(account.tenant_id),
        username=account.username,
    )

    return LoginResponse(
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
    )


@router.post("/auth/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    current_account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(db_manager.get_session),
):
    if current_account.password != payload.current_password:
        raise HTTPException(status_code=400, detail="current password is incorrect")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="new password must be different")

    current_account.password = payload.new_password
    await session.commit()
    return {"message": "password updated"}
