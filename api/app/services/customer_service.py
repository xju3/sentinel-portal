"""
Customer service - business logic for customer operations
"""

from uuid import UUID
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, or_

from app.models.customer import (
    Tenant,
    TenantSensor,
    Supplier,
    Contact,
    Account,
    Area,
    Location,
    HealthCheckFreq,
)
from app.utils.exceptions import DomainException

from app.models.sensor import SensorMonitoring, Sensor
from app.models.device import DeviceCategory, DeviceSpec, DeviceInst

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
    async def get_suppliers(
        session: AsyncSession,
        tenant_id: UUID,
        skip: int,
        limit: int,
        keyword: Optional[str] = None,
    ) -> List[Supplier]:
        stmt = select(Supplier).where(Supplier.tenant_id == tenant_id)
        if keyword:
            like_kw = f"%{keyword.strip()}%"
            stmt = stmt.where(
                or_(
                    Supplier.name.ilike(like_kw),
                    Supplier.brand.ilike(like_kw),
                    Supplier.contact_info.ilike(like_kw),
                )
            )
        stmt = stmt.offset(skip).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def count_suppliers(
        session: AsyncSession,
        tenant_id: UUID,
        keyword: Optional[str] = None,
    ) -> int:
        stmt = select(func.count(Supplier.id)).where(Supplier.tenant_id == tenant_id)
        if keyword:
            like_kw = f"%{keyword.strip()}%"
            stmt = stmt.where(
                or_(
                    Supplier.name.ilike(like_kw),
                    Supplier.brand.ilike(like_kw),
                    Supplier.contact_info.ilike(like_kw),
                )
            )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def get_supplier(
        session: AsyncSession,
        tenant_id: UUID,
        supplier_id: UUID,
    ) -> Optional[Supplier]:
        stmt = select(Supplier).where(
            Supplier.id == supplier_id,
            Supplier.tenant_id == tenant_id,
        )
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
    async def delete_account(session: AsyncSession, db_account: Account) -> None:
        await session.delete(db_account)
        await session.commit()


class AreaService:
    @staticmethod
    async def get_areas(
        session: AsyncSession,
        tenant_id: UUID,
        skip: int,
        limit: int,
    ) -> List[Area]:
        stmt = (
            select(Area)
            .where(Area.tenant_id == tenant_id)
            .offset(skip)
            .limit(limit)
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_area(
        session: AsyncSession,
        tenant_id: UUID,
        area_id: UUID,
    ) -> Optional[Area]:
        stmt = select(Area).where(
            Area.id == area_id,
            Area.tenant_id == tenant_id,
        )
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
    async def update_area(
        session: AsyncSession,
        db_area: Area,
        data: dict,
    ) -> Area:
        for key, value in data.items():
            setattr(db_area, key, value)
        await session.commit()
        await session.refresh(db_area)
        return db_area

    @staticmethod
    async def delete_area(session: AsyncSession, db_area: Area) -> None:
        await session.delete(db_area)
        await session.commit()


class LocationService:
    @staticmethod
    async def get_locations(
        session: AsyncSession,
        tenant_id: UUID,
        skip: int,
        limit: int,
    ) -> List[Location]:
        stmt = (
            select(Location)
            .where(Location.tenant_id == tenant_id)
            .offset(skip)
            .limit(limit)
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_location(
        session: AsyncSession,
        tenant_id: UUID,
        location_id: UUID,
    ) -> Optional[Location]:
        stmt = select(Location).where(
            Location.id == location_id,
            Location.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def is_tenant_location(
        session: AsyncSession,
        tenant_id: UUID,
        location_id: UUID,
    ) -> bool:
        """Check if a location belongs to the given tenant."""
        stmt = select(Location.id).where(
            Location.id == location_id,
            Location.tenant_id == tenant_id,
        ).limit(1)
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def get_paged_locations(
        session: AsyncSession,
        tenant_id: UUID,
        current: int,
        page_size: int,
        keyword: Optional[str] = None,
    ) -> tuple:
        """Get paged locations with total count. Returns (items, total)."""
        base_stmt = select(Location).where(Location.tenant_id == tenant_id)
        if keyword:
            like = f"%{keyword}%"
            base_stmt = base_stmt.where(Location.name.ilike(like))

        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        count_result = await session.execute(count_stmt)
        total = count_result.scalar() or 0

        skip = (current - 1) * page_size
        fetch_stmt = base_stmt.offset(skip).limit(page_size)
        result = await session.execute(fetch_stmt)
        items = result.scalars().all()

        return items, total

    @staticmethod
    async def create_location(session: AsyncSession, data: dict) -> Location:
        db_obj = Location(**data)
        session.add(db_obj)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def update_location(
        session: AsyncSession,
        db_obj: Location,
        data: dict,
    ) -> Location:
        for key, value in data.items():
            setattr(db_obj, key, value)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def delete_location(session: AsyncSession, db_obj: Location) -> None:
        await session.delete(db_obj)
        await session.commit()


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
        tenant_host: str,
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
            "host": tenant_host,
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


class HealthCheckFreqService:

    @staticmethod
    async def get_health_check_by_sensor_sn(
        session: AsyncSession,
        sn: str,
    ) -> Optional[HealthCheckFreq]:
        
        stmt = (
            select(HealthCheckFreq)
            .join(DeviceCategory, DeviceCategory.health_check_freq_id == HealthCheckFreq.id)
            .join(DeviceSpec, DeviceSpec.device_category_id == DeviceCategory.id)
            .join(DeviceInst, DeviceInst.device_spec_id == DeviceSpec.id)
            .join(SensorMonitoring, SensorMonitoring.device_inst_id == DeviceInst.id and SensorMonitoring.status == 1)  # 只考虑状态为1的监测
            .join(Sensor, Sensor.id == SensorMonitoring.sensor_id)
            .where(Sensor.sn == sn)
        )
        
        result = await session.execute(stmt)
        # 同样使用第一问提到的 scalars().first() 或 scalar_one_or_none()
        return result.scalars().first()

    @staticmethod
    async def get_health_check_freqs(
        session: AsyncSession,
        tenant_id: UUID,
        skip: int,
        limit: int,
    ) -> List[HealthCheckFreq]:
        stmt = (
            select(HealthCheckFreq)
            .where(HealthCheckFreq.tenant_id == tenant_id)
            .offset(skip)
            .limit(limit)
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_health_check_freq(
        session: AsyncSession,
        tenant_id: UUID,
        freq_id: UUID,
    ) -> Optional[HealthCheckFreq]:
        stmt = select(HealthCheckFreq).where(
            HealthCheckFreq.id == freq_id,
            HealthCheckFreq.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create_health_check_freq(session: AsyncSession, data: dict) -> HealthCheckFreq:
        db_freq = HealthCheckFreq(**data)
        session.add(db_freq)
        await session.commit()
        await session.refresh(db_freq)
        return db_freq

    @staticmethod
    async def update_health_check_freq(
        session: AsyncSession,
        db_freq: HealthCheckFreq,
        data: dict,
    ) -> HealthCheckFreq:
        for key, value in data.items():
            setattr(db_freq, key, value)
        await session.commit()
        await session.refresh(db_freq)
        return db_freq

    @staticmethod
    async def delete_health_check_freq(session: AsyncSession, db_freq: HealthCheckFreq) -> None:
        await session.delete(db_freq)
        await session.commit()
