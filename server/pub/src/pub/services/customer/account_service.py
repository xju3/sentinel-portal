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

class AccountService:
    @staticmethod
    async def get_accounts(
        session: AsyncSession,
        skip: int,
        limit: int,
        sort_by: str | None = None,
        sort_order: str = "ascend",
    ) -> List[Account]:
        stmt = select(Account)
        stmt = apply_sorting(stmt, Account, sort_by, sort_order)
        stmt = stmt.offset(skip).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_account(session: AsyncSession, account_id: UUID) -> Optional[Account]:
        stmt = select(Account).where(Account.id == account_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_admin_accounts(session: AsyncSession) -> List[Account]:
        stmt = select(Account).where(Account.admin == True)  # noqa: E712
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_admin_account(session: AsyncSession, account_id: UUID) -> Optional[Account]:
        stmt = select(Account).where(
            Account.id == account_id,
            Account.admin == True,  # noqa: E712
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_tenant_accounts(session: AsyncSession, tenant_id: UUID) -> List[Account]:
        stmt = select(Account).where(Account.tenant_id == tenant_id)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_tenant_account(session: AsyncSession, account_id: UUID, tenant_id: UUID) -> Optional[Account]:
        stmt = select(Account).where(
            Account.id == account_id,
            Account.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_contacts_by_ids(session: AsyncSession, contact_ids: List[UUID]) -> dict:
        """Batch fetch contacts by IDs and return a dict of {id: name}."""
        if not contact_ids:
            return {}
        stmt = select(Contact).where(Contact.id.in_(contact_ids))
        result = await session.execute(stmt)
        return {c.id: c.name for c in result.scalars().all()}

    @staticmethod
    async def create_account(session: AsyncSession, data: dict) -> Account:
        db_account = Account(**data)
        session.add(db_account)
        await session.commit()
        await session.refresh(db_account)
        return db_account

    @staticmethod
    async def update_account(session: AsyncSession, db_account: Account, data: dict) -> Account:
        for key, value in data.items():
            setattr(db_account, key, value)
        await session.commit()
        await session.refresh(db_account)
        return db_account

    @staticmethod
    async def unbind_account_wx(session: AsyncSession, db_account: Account) -> Account:
        db_account.wx_user_id = None
        await session.commit()
        await session.refresh(db_account)
        return db_account

    @staticmethod
    async def delete_account(session: AsyncSession, db_account: Account) -> None:
        await session.delete(db_account)
        await session.commit()
