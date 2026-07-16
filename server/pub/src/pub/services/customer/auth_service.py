"""
Customer service - business logic for customer operations
"""

from uuid import UUID
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, or_

from pub.models.customer import (
    Region,
    Tenant,
    TenantSensor,
    Supplier,
    Contact,
    Account,
    Area,
    Location,
    HealthCheckFreq,
    IsoStandard,
)
from pub.exceptions.domain_exception import DomainException
from pub.utils.sorting import apply_sorting

from pub.models.sensor import SensorMonitoring, Sensor
from pub.models.device import DeviceCategory, DeviceSpec, DeviceInst

class AuthService:
    """Service for authentication operations."""

    @staticmethod
    async def get_account_by_username(
        session: AsyncSession, username: str
    ) -> Optional[Account]:
        stmt = select(Account).where(Account.username == username)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_account_by_email(
        session: AsyncSession, email: str
    ) -> Optional[Account]:
        stmt = select(Account).where(Account.email == email)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_contact_by_email(
        session: AsyncSession, email: str
    ) -> Optional[Contact]:
        stmt = select(Contact).where(Contact.email == email)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_account_by_mobile(
        session: AsyncSession, mobile: str
    ) -> Optional[Account]:
        stmt = select(Account).where(Account.mobile == mobile)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_contact_by_mobile(
        session: AsyncSession, mobile: str
    ) -> Optional[Contact]:
        stmt = select(Contact).where(Contact.mobile == mobile)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_tenant_by_code(
        session: AsyncSession, code: str
    ) -> Optional[Tenant]:
        stmt = select(Tenant).where(Tenant.code == code)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_account(
        session: AsyncSession, account_id: UUID
    ) -> Optional[Account]:
        stmt = select(Account).where(Account.id == account_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_account_by_credentials(
        session: AsyncSession, username: str, password: str
    ) -> Optional[Account]:
        stmt = select(Account).where(
            Account.username == username,
            Account.password == password,
            Account.active == True,  # noqa: E712
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_tenant_by_id(
        session: AsyncSession, tenant_id: UUID
    ) -> Optional[Tenant]:
        stmt = select(Tenant).where(Tenant.id == tenant_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_contact_by_id(
        session: AsyncSession, contact_id: UUID
    ) -> Optional[Contact]:
        stmt = select(Contact).where(Contact.id == contact_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create_tenant(session: AsyncSession, data: dict) -> Tenant:
        """Create a new tenant with proper defaults.

        Ensures create_at and start_at are set to today's date if not provided.
        """
        from datetime import date

        today = date.today()
        data.setdefault("create_at", today)
        data.setdefault("start_at", today)

        db_tenant = Tenant(**data)
        session.add(db_tenant)
        await session.commit()
        await session.refresh(db_tenant)
        return db_tenant

    @staticmethod
    async def create_contact(session: AsyncSession, data: dict) -> Contact:
        db_contact = Contact(**data)
        session.add(db_contact)
        await session.flush()
        return db_contact

    @staticmethod
    async def create_account(session: AsyncSession, data: dict) -> Account:
        db_account = Account(**data)
        session.add(db_account)
        await session.flush()
        return db_account

    @staticmethod
    async def update_account_password(
        session: AsyncSession, account: Account, new_password: str
    ) -> None:
        account.password = new_password
        await session.commit()

    @staticmethod
    async def get_account_by_wx_user_id(
        session: AsyncSession, wx_user_id: str
    ) -> Optional[Account]:
        stmt = select(Account).where(Account.wx_user_id == wx_user_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def bind_account_wx(
        session: AsyncSession, account: Account, wx_user_id: str
    ) -> None:
        account.wx_user_id = wx_user_id
        await session.commit()

    @staticmethod
    async def commit(session: AsyncSession) -> None:
        await session.commit()

    @staticmethod
    async def rollback(session: AsyncSession) -> None:
        await session.rollback()

    @staticmethod
    async def register(
        session: AsyncSession,
        username: str,
        email: Optional[str],
        normalized_phone: str,
        company_name: str,
        contact_name: str,
        login_channel: str,
        account_flag: int,
        tenant_code: str,
        tenant_mqtt_server: str,
        tenant_api_server: str,
        random_password: str,
    ) -> dict:
        """Complete registration business logic with all validations.

        Raises DomainException if any uniqueness constraint is violated.
        """
        # Check username uniqueness
        existing_username = await AuthService.get_account_by_username(session, username)
        if existing_username is not None:
            raise DomainException(code=409, message="account username already exists")

        # Check email uniqueness
        if email:
            existing_email = await AuthService.get_account_by_email(session, email)
            if existing_email is not None:
                raise DomainException(code=409, message="email already exists")
            existing_contact_email = await AuthService.get_contact_by_email(session, email)
            if existing_contact_email is not None:
                raise DomainException(code=409, message="email already exists")

        # Check phone uniqueness
        existing_mobile = await AuthService.get_account_by_mobile(session, normalized_phone)
        if existing_mobile is not None:
            raise DomainException(code=409, message="phone already exists")
        existing_contact_mobile = await AuthService.get_contact_by_mobile(session, normalized_phone)
        if existing_contact_mobile is not None:
            raise DomainException(code=409, message="phone already exists")

        # Create tenant, contact, account
        tenant = await AuthService.create_tenant(session, {
            "code": tenant_code,
            "name": company_name,
            "mqtt_server": tenant_mqtt_server,
            "api_server": tenant_api_server,
            "active": True,
        })

        contact = await AuthService.create_contact(session, {
            "name": contact_name,
            "mobile": normalized_phone,
            "email": email,
            "active": True,
            "tenant_id": tenant.id,
        })

        account = await AuthService.create_account(session, {
            "username": username,
            "password": random_password,
            "email": email,
            "mobile": normalized_phone,
            "flag": account_flag,
            "active": True,
            "admin": False,
            "contact_id": contact.id,
            "tenant_id": tenant.id,
        })

        return {
            "tenant_id": tenant.id,
            "contact_id": contact.id,
            "account_id": account.id,
            "account_username": account.username,
            "login_channel": login_channel,
            "generated_password": random_password,
        }
