"""
Customer service - business logic for customer operations
"""

from uuid import UUID
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.customer import (
    Tenant,
    TenantSensor,
    Supplier,
    Contact,
    Account,
    Area,
    HealthCheckFreq,
)


class TenantService:
    @staticmethod
    async def get_tenants(session: AsyncSession, skip: int, limit: int) -> List[Tenant]:
        stmt = select(Tenant).offset(skip).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_tenant(session: AsyncSession, tenant_id: UUID) -> Optional[Tenant]:
        stmt = select(Tenant).where(Tenant.id == tenant_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create_tenant(session: AsyncSession, data: dict) -> Tenant:
        db_tenant = Tenant(**data)
        session.add(db_tenant)
        await session.commit()
        await session.refresh(db_tenant)
        return db_tenant

    @staticmethod
    async def update_tenant(session: AsyncSession, db_tenant: Tenant, data: dict) -> Tenant:
        for key, value in data.items():
            setattr(db_tenant, key, value)
        await session.commit()
        await session.refresh(db_tenant)
        return db_tenant

    @staticmethod
    async def delete_tenant(session: AsyncSession, db_tenant: Tenant) -> None:
        await session.delete(db_tenant)
        await session.commit()


class TenantSensorService:
    @staticmethod
    async def get_tenant_sensors(session: AsyncSession, skip: int, limit: int) -> List[TenantSensor]:
        stmt = select(TenantSensor).offset(skip).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_tenant_sensor(session: AsyncSession, ts_id: UUID) -> Optional[TenantSensor]:
        stmt = select(TenantSensor).where(TenantSensor.id == ts_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create_tenant_sensor(session: AsyncSession, data: dict) -> TenantSensor:
        db_ts = TenantSensor(**data)
        session.add(db_ts)
        await session.commit()
        await session.refresh(db_ts)
        return db_ts

    @staticmethod
    async def update_tenant_sensor(session: AsyncSession, db_ts: TenantSensor, data: dict) -> TenantSensor:
        for key, value in data.items():
            setattr(db_ts, key, value)
        await session.commit()
        await session.refresh(db_ts)
        return db_ts

    @staticmethod
    async def delete_tenant_sensor(session: AsyncSession, db_ts: TenantSensor) -> None:
        await session.delete(db_ts)
        await session.commit()


class SupplierService:
    @staticmethod
    async def get_suppliers(session: AsyncSession, skip: int, limit: int) -> List[Supplier]:
        stmt = select(Supplier).offset(skip).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_supplier(session: AsyncSession, supplier_id: UUID) -> Optional[Supplier]:
        stmt = select(Supplier).where(Supplier.id == supplier_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create_supplier(session: AsyncSession, data: dict) -> Supplier:
        db_supplier = Supplier(**data)
        session.add(db_supplier)
        await session.commit()
        await session.refresh(db_supplier)
        return db_supplier

    @staticmethod
    async def update_supplier(session: AsyncSession, db_supplier: Supplier, data: dict) -> Supplier:
        for key, value in data.items():
            setattr(db_supplier, key, value)
        await session.commit()
        await session.refresh(db_supplier)
        return db_supplier

    @staticmethod
    async def delete_supplier(session: AsyncSession, db_supplier: Supplier) -> None:
        await session.delete(db_supplier)
        await session.commit()


class ContactService:
    @staticmethod
    async def get_contacts(session: AsyncSession, skip: int, limit: int) -> List[Contact]:
        stmt = select(Contact).offset(skip).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def create_contact(session: AsyncSession, data: dict) -> Contact:
        db_contact = Contact(**data)
        session.add(db_contact)
        await session.commit()
        await session.refresh(db_contact)
        return db_contact


class AccountService:
    @staticmethod
    async def get_accounts(session: AsyncSession, skip: int, limit: int) -> List[Account]:
        stmt = select(Account).offset(skip).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_account(session: AsyncSession, account_id: UUID) -> Optional[Account]:
        stmt = select(Account).where(Account.id == account_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

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
    async def delete_account(session: AsyncSession, db_account: Account) -> None:
        await session.delete(db_account)
        await session.commit()


class AreaService:
    @staticmethod
    async def get_areas(session: AsyncSession, skip: int, limit: int) -> List[Area]:
        stmt = select(Area).offset(skip).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_area(session: AsyncSession, area_id: UUID) -> Optional[Area]:
        stmt = select(Area).where(Area.id == area_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create_area(session: AsyncSession, data: dict) -> Area:
        db_area = Area(**data)
        session.add(db_area)
        await session.commit()
        await session.refresh(db_area)
        return db_area

    @staticmethod
    async def delete_area(session: AsyncSession, db_area: Area) -> None:
        await session.delete(db_area)
        await session.commit()


class HealthCheckFreqService:
    @staticmethod
    async def get_health_check_freqs(session: AsyncSession, skip: int, limit: int) -> List[HealthCheckFreq]:
        stmt = select(HealthCheckFreq).offset(skip).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def create_health_check_freq(session: AsyncSession, data: dict) -> HealthCheckFreq:
        db_freq = HealthCheckFreq(**data)
        session.add(db_freq)
        await session.commit()
        await session.refresh(db_freq)
        return db_freq
