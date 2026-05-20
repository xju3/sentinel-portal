"""
Customer related management endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from uuid import UUID

from app.database import db_manager
from app.models.customer import Account as AccountModel, Location, Tenant
from app.services.customer_service import (
    TenantService,
    TenantSensorService,
    SupplierService,
    AccountService,
    AreaService,
    LocationService,
    HealthCheckFreqService,
)
from app.utils.auth import get_current_account

router = APIRouter(tags=["customers"])


# ==========================================
# 1. Tenant
# ==========================================
class TenantCreate(BaseModel):
    code: str
    name: str
    host: str
    active: Optional[bool] = True


class TenantUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    host: Optional[str] = None
    active: Optional[bool] = None


class TenantResponse(BaseModel):
    id: UUID
    code: str
    name: str
    host: str
    active: bool

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 1b. Current Tenant (authenticated) - MUST be defined before /tenants/{tenant_id}
# ==========================================
class CurrentTenantUpdate(BaseModel):
    name: Optional[str] = None
    host: Optional[str] = None


@router.get("/tenants/current", response_model=TenantResponse)
async def get_current_tenant(
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(db_manager.get_session),
):
    tenant = await TenantService.get_tenant(session, current_account.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


@router.put("/tenants/current", response_model=TenantResponse)
async def update_current_tenant(
    payload: CurrentTenantUpdate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(db_manager.get_session),
):
    tenant = await TenantService.get_tenant(session, current_account.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    update_data = payload.model_dump(exclude_unset=True)
    return await TenantService.update_tenant(session, tenant, update_data)


@router.get("/tenants", response_model=List[TenantResponse])
async def list_tenants(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(db_manager.get_session),
):
    return await TenantService.get_tenants(session, skip, limit)


@router.get("/tenants/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: UUID,
    session: AsyncSession = Depends(db_manager.get_session),
):
    tenant = await TenantService.get_tenant(session, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


@router.post("/tenants", response_model=TenantResponse)
async def create_tenant(
    tenant: TenantCreate,
    session: AsyncSession = Depends(db_manager.get_session),
):
    return await TenantService.create_tenant(session, tenant.model_dump())


@router.put("/tenants/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: UUID,
    tenant: TenantUpdate,
    session: AsyncSession = Depends(db_manager.get_session),
):
    db_tenant = await TenantService.get_tenant(session, tenant_id)
    if not db_tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    update_data = tenant.model_dump(exclude_unset=True)
    return await TenantService.update_tenant(session, db_tenant, update_data)


@router.delete("/tenants/{tenant_id}")
async def delete_tenant(
    tenant_id: UUID,
    session: AsyncSession = Depends(db_manager.get_session),
):
    db_tenant = await TenantService.get_tenant(session, tenant_id)
    if not db_tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    await TenantService.delete_tenant(session, db_tenant)
    return {"message": "Tenant deleted successfully"}


# ==========================================
# 2. TenantSensor
# ==========================================
class TenantSensorCreate(BaseModel):
    tenant_id: UUID
    sensor_id: UUID
    available: Optional[bool] = True


class TenantSensorUpdate(BaseModel):
    available: Optional[bool] = None


class TenantSensorResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    sensor_id: UUID
    available: bool

    model_config = ConfigDict(from_attributes=True)


@router.get("/tenant-sensors", response_model=List[TenantSensorResponse])
async def list_tenant_sensors(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(db_manager.get_session),
):
    return await TenantSensorService.get_tenant_sensors(session, skip, limit)


@router.get("/tenant-sensors/{ts_id}", response_model=TenantSensorResponse)
async def get_tenant_sensor(
    ts_id: UUID,
    session: AsyncSession = Depends(db_manager.get_session),
):
    ts = await TenantSensorService.get_tenant_sensor(session, ts_id)
    if not ts:
        raise HTTPException(status_code=404, detail="TenantSensor not found")
    return ts


@router.post("/tenant-sensors", response_model=TenantSensorResponse)
async def create_tenant_sensor(
    ts: TenantSensorCreate,
    session: AsyncSession = Depends(db_manager.get_session),
):
    return await TenantSensorService.create_tenant_sensor(session, ts.model_dump())


@router.put("/tenant-sensors/{ts_id}", response_model=TenantSensorResponse)
async def update_tenant_sensor(
    ts_id: UUID,
    ts: TenantSensorUpdate,
    session: AsyncSession = Depends(db_manager.get_session),
):
    db_ts = await TenantSensorService.get_tenant_sensor(session, ts_id)
    if not db_ts:
        raise HTTPException(status_code=404, detail="TenantSensor not found")

    update_data = ts.model_dump(exclude_unset=True)
    return await TenantSensorService.update_tenant_sensor(session, db_ts, update_data)


@router.delete("/tenant-sensors/{ts_id}")
async def delete_tenant_sensor(
    ts_id: UUID,
    session: AsyncSession = Depends(db_manager.get_session),
):
    db_ts = await TenantSensorService.get_tenant_sensor(session, ts_id)
    if not db_ts:
        raise HTTPException(status_code=404, detail="TenantSensor not found")

    await TenantSensorService.delete_tenant_sensor(session, db_ts)
    return {"message": "TenantSensor deleted successfully"}


# ==========================================
# 3. Supplier
# ==========================================
class SupplierCreate(BaseModel):
    name: str
    brand: str
    contact_info: Optional[str] = None
    active: Optional[bool] = True
    tenant_id: Optional[UUID] = None


class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    brand: Optional[str] = None
    contact_info: Optional[str] = None
    active: Optional[bool] = None


class SupplierResponse(BaseModel):
    id: UUID
    name: str
    brand: str
    contact_info: Optional[str] = None
    active: bool
    tenant_id: UUID

    model_config = ConfigDict(from_attributes=True)


class PagedCountResponse(BaseModel):
    total: int


@router.get("/suppliers", response_model=List[SupplierResponse])
async def list_suppliers(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    keyword: Optional[str] = Query(None),
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(db_manager.get_session),
):
    tenant_id = current_account.tenant_id
    return await SupplierService.get_suppliers(session, tenant_id, skip, limit, keyword)


@router.get("/suppliers/count", response_model=PagedCountResponse)
async def count_suppliers(
    keyword: Optional[str] = Query(None),
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(db_manager.get_session),
):
    tenant_id = current_account.tenant_id
    total = await SupplierService.count_suppliers(session, tenant_id, keyword)
    return {"total": total}


@router.get("/suppliers/{supplier_id}", response_model=SupplierResponse)
async def get_supplier(
    supplier_id: UUID,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(db_manager.get_session),
):
    tenant_id = current_account.tenant_id
    supplier = await SupplierService.get_supplier(session, tenant_id, supplier_id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return supplier


@router.post("/suppliers", response_model=SupplierResponse)
async def create_supplier(
    supplier: SupplierCreate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(db_manager.get_session),
):
    tenant_id = current_account.tenant_id
    payload = supplier.model_dump(exclude_unset=True)
    if "tenant_id" in payload and payload["tenant_id"] is not None and payload["tenant_id"] != tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id mismatch")
    payload["tenant_id"] = tenant_id
    return await SupplierService.create_supplier(session, payload)


@router.put("/suppliers/{supplier_id}", response_model=SupplierResponse)
async def update_supplier(
    supplier_id: UUID,
    supplier: SupplierUpdate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(db_manager.get_session),
):
    tenant_id = current_account.tenant_id
    db_supplier = await SupplierService.get_supplier(session, tenant_id, supplier_id)
    if not db_supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    update_data = supplier.model_dump(exclude_unset=True)
    return await SupplierService.update_supplier(session, db_supplier, update_data)


@router.delete("/suppliers/{supplier_id}")
async def delete_supplier(
    supplier_id: UUID,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(db_manager.get_session),
):
    tenant_id = current_account.tenant_id
    db_supplier = await SupplierService.get_supplier(session, tenant_id, supplier_id)
    if not db_supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    await SupplierService.delete_supplier(session, db_supplier)
    return {"message": "Supplier deleted successfully"}


# ==========================================
# 4. Account
# ==========================================
class AccountCreate(BaseModel):
    username: str
    password: str
    flag: Optional[int] = 2
    active: Optional[bool] = True
    contact_id: Optional[UUID] = None
    tenant_id: UUID


class AccountUpdate(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    flag: Optional[int] = None
    active: Optional[bool] = None
    contact_id: Optional[UUID] = None


class AccountResponse(BaseModel):
    id: UUID
    username: str
    flag: int
    active: bool
    admin: Optional[bool] = False
    contact_id: Optional[UUID] = None
    contact_name: Optional[str] = None
    tenant_id: UUID
    # 响应中不包含 password 字段

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 4b. Tenant-scoped Account (authenticated) - MUST be defined before /accounts/{account_id}
# ==========================================
class TenantAccountCreate(BaseModel):
    contact_name: str
    username: str
    password: str
    flag: Optional[int] = 2
    active: Optional[bool] = True


@router.get("/accounts/by-tenant", response_model=List[AccountResponse])
async def list_tenant_accounts(
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(db_manager.get_session),
):
    """List all accounts belonging to the current tenant"""
    from app.models.customer import Contact as ContactModel

    stmt = select(AccountModel).where(AccountModel.tenant_id == current_account.tenant_id)
    result = await session.execute(stmt)
    accounts = result.scalars().all()

    # 获取所有关联的 contact_id 并批量查询 contact_name
    contact_ids = [a.contact_id for a in accounts if a.contact_id]
    contact_map = {}
    if contact_ids:
        contact_stmt = select(ContactModel).where(ContactModel.id.in_(contact_ids))
        contact_result = await session.execute(contact_stmt)
        for c in contact_result.scalars().all():
            contact_map[c.id] = c.name

    # 构建响应，填充 contact_name
    response = []
    for a in accounts:
        resp = AccountResponse(
            id=a.id,
            username=a.username,
            flag=a.flag,
            active=a.active,
            admin=a.admin,
            contact_id=a.contact_id,
            contact_name=contact_map.get(a.contact_id) if a.contact_id else None,
            tenant_id=a.tenant_id,
        )
        response.append(resp)
    return response


@router.post("/accounts/by-tenant", response_model=AccountResponse)
async def create_tenant_account(
    payload: TenantAccountCreate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(db_manager.get_session),
):
    """Create a new account under the current tenant"""
    from app.models.customer import Contact as ContactModel
    from app.services.customer_service import ContactService

    # 1. 先创建 Contact
    contact_data = {
        "name": payload.contact_name,
        "tenant_id": current_account.tenant_id,
    }
    contact = await ContactService.create_contact(session, contact_data)

    # 2. 再创建 Account，关联 contact_id
    data = payload.model_dump(exclude={"contact_name"})
    data["tenant_id"] = current_account.tenant_id
    data["contact_id"] = contact.id
    account = await AccountService.create_account(session, data)

    # 3. 返回完整响应
    return AccountResponse(
        id=account.id,
        username=account.username,
        flag=account.flag,
        active=account.active,
        admin=account.admin,
        contact_id=account.contact_id,
        contact_name=contact.name,
        tenant_id=account.tenant_id,
    )


@router.put("/accounts/by-tenant/{account_id}", response_model=AccountResponse)
async def update_tenant_account(
    account_id: UUID,
    payload: AccountUpdate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(db_manager.get_session),
):
    """Update an account belonging to the current tenant (e.g. toggle active)"""
    stmt = select(AccountModel).where(
        AccountModel.id == account_id,
        AccountModel.tenant_id == current_account.tenant_id,
    )
    result = await session.execute(stmt)
    db_account = result.scalar_one_or_none()
    if not db_account:
        raise HTTPException(status_code=404, detail="Account not found")

    update_data = payload.model_dump(exclude_unset=True)
    # 不允许通过此接口修改 tenant_id
    update_data.pop("tenant_id", None)
    return await AccountService.update_account(session, db_account, update_data)


@router.put("/accounts/by-tenant/{account_id}/password")
async def update_tenant_account_password(
    account_id: UUID,
    payload: AccountUpdate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(db_manager.get_session),
):
    """Update password for an account belonging to the current tenant"""
    stmt = select(AccountModel).where(
        AccountModel.id == account_id,
        AccountModel.tenant_id == current_account.tenant_id,
    )
    result = await session.execute(stmt)
    db_account = result.scalar_one_or_none()
    if not db_account:
        raise HTTPException(status_code=404, detail="Account not found")

    update_data = payload.model_dump(exclude_unset=True)
    if "password" not in update_data or not update_data["password"]:
        raise HTTPException(status_code=400, detail="Password is required")

    return await AccountService.update_account(session, db_account, update_data)


@router.delete("/accounts/by-tenant/{account_id}")
async def delete_tenant_account(
    account_id: UUID,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(db_manager.get_session),
):
    """Delete an account belonging to the current tenant"""
    stmt = select(AccountModel).where(
        AccountModel.id == account_id,
        AccountModel.tenant_id == current_account.tenant_id,
    )
    result = await session.execute(stmt)
    db_account = result.scalar_one_or_none()
    if not db_account:
        raise HTTPException(status_code=404, detail="Account not found")

    await AccountService.delete_account(session, db_account)
    return {"message": "Account deleted successfully"}


@router.get("/accounts", response_model=List[AccountResponse])
async def list_accounts(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(db_manager.get_session),
):
    return await AccountService.get_accounts(session, skip, limit)


@router.get("/accounts/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: UUID,
    session: AsyncSession = Depends(db_manager.get_session),
):
    account = await AccountService.get_account(session, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.post("/accounts", response_model=AccountResponse)
async def create_account(
    account: AccountCreate,
    session: AsyncSession = Depends(db_manager.get_session),
):
    # 在实际应用中, 此处通常需对 password 进行哈希处理
    return await AccountService.create_account(session, account.model_dump())


@router.put("/accounts/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: UUID,
    account: AccountUpdate,
    session: AsyncSession = Depends(db_manager.get_session),
):
    db_account = await AccountService.get_account(session, account_id)
    if not db_account:
        raise HTTPException(status_code=404, detail="Account not found")

    update_data = account.model_dump(exclude_unset=True)
    # 实际项目中如果修改 password，也需重新哈希处理
    return await AccountService.update_account(session, db_account, update_data)


@router.delete("/accounts/{account_id}")
async def delete_account(
    account_id: UUID,
    session: AsyncSession = Depends(db_manager.get_session),
):
    db_account = await AccountService.get_account(session, account_id)
    if not db_account:
        raise HTTPException(status_code=404, detail="Account not found")

    await AccountService.delete_account(session, db_account)
    return {"message": "Account deleted successfully"}


# ==========================================
# 5. Area
# ==========================================
class AreaCreate(BaseModel):
    name: str
    description: Optional[str] = None
    ssid: Optional[str] = None
    passwd: Optional[str] = None
    parent_id: Optional[UUID] = None
    tenant_id: Optional[UUID] = None


class AreaUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    ssid: Optional[str] = None
    passwd: Optional[str] = None
    parent_id: Optional[UUID] = None
    tenant_id: Optional[UUID] = None


class AreaResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    ssid: Optional[str] = None
    passwd: Optional[str] = None
    parent_id: Optional[UUID] = None
    tenant_id: UUID

    model_config = ConfigDict(from_attributes=True)


@router.get("/areas", response_model=List[AreaResponse])
async def list_areas(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(db_manager.get_session),
):
    tenant_id = current_account.tenant_id
    return await AreaService.get_areas(session, tenant_id, skip, limit)


@router.post("/areas", response_model=AreaResponse)
async def create_area(
    area: AreaCreate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(db_manager.get_session),
):
    tenant_id = current_account.tenant_id
    payload = area.model_dump(exclude_unset=True)
    if "tenant_id" in payload and payload["tenant_id"] is not None and payload["tenant_id"] != tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id mismatch")
    payload["tenant_id"] = tenant_id
    return await AreaService.create_area(session, payload)


@router.put("/areas/{area_id}", response_model=AreaResponse)
async def update_area(
    area_id: UUID,
    area: AreaUpdate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(db_manager.get_session),
):
    tenant_id = current_account.tenant_id
    db_area = await AreaService.get_area(session, tenant_id, area_id)
    if not db_area:
        raise HTTPException(status_code=404, detail="Area not found")

    update_data = area.model_dump(exclude_unset=True)
    if "tenant_id" in update_data and update_data["tenant_id"] != tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id cannot be changed")
    update_data.pop("tenant_id", None)
    return await AreaService.update_area(session, db_area, update_data)


@router.delete("/areas/{area_id}")
async def delete_area(
    area_id: UUID,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(db_manager.get_session),
):
    tenant_id = current_account.tenant_id
    db_area = await AreaService.get_area(session, tenant_id, area_id)
    if not db_area:
        raise HTTPException(status_code=404, detail="Area not found")

    await AreaService.delete_area(session, db_area)
    return {"message": "Area deleted successfully"}


# ==========================================
# 6. Location
# ==========================================
class LocationCreate(BaseModel):
    name: str
    description: Optional[str] = None
    status: Optional[int] = 1
    tenant_id: Optional[UUID] = None


class LocationUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[int] = None
    tenant_id: Optional[UUID] = None


class LocationResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    status: int
    tenant_id: UUID

    model_config = ConfigDict(from_attributes=True)


class PagedLocationResponse(BaseModel):
    items: List[LocationResponse]
    total: int


@router.get("/locations", response_model=PagedLocationResponse)
async def list_locations(
    current: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    keyword: Optional[str] = Query(None),
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(db_manager.get_session),
):
    tenant_id = current_account.tenant_id
    base_stmt = select(Location).where(Location.tenant_id == tenant_id)
    if keyword:
        like = f"%{keyword}%"
        base_stmt = base_stmt.where(Location.name.ilike(like))

    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    count_result = await session.execute(count_stmt)
    total = count_result.scalar() or 0

    skip = (current - 1) * pageSize
    fetch_stmt = base_stmt.offset(skip).limit(pageSize)
    result = await session.execute(fetch_stmt)
    items = result.scalars().all()

    return PagedLocationResponse(items=items, total=total)


@router.post("/locations", response_model=LocationResponse)
async def create_location(
    location: LocationCreate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(db_manager.get_session),
):
    tenant_id = current_account.tenant_id
    payload = location.model_dump(exclude_unset=True)
    if "tenant_id" in payload and payload["tenant_id"] is not None and payload["tenant_id"] != tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id mismatch")
    payload["tenant_id"] = tenant_id
    return await LocationService.create_location(session, payload)


@router.put("/locations/{location_id}", response_model=LocationResponse)
async def update_location(
    location_id: UUID,
    location: LocationUpdate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(db_manager.get_session),
):
    tenant_id = current_account.tenant_id
    db_obj = await LocationService.get_location(session, tenant_id, location_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Location not found")

    update_data = location.model_dump(exclude_unset=True)
    if "tenant_id" in update_data and update_data["tenant_id"] != tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id cannot be changed")
    update_data.pop("tenant_id", None)
    return await LocationService.update_location(session, db_obj, update_data)


@router.delete("/locations/{location_id}")
async def delete_location(
    location_id: UUID,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(db_manager.get_session),
):
    tenant_id = current_account.tenant_id
    db_obj = await LocationService.get_location(session, tenant_id, location_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Location not found")

    await LocationService.delete_location(session, db_obj)
    return {"message": "Location deleted successfully"}


# ==========================================
# 7. HealthCheckFreq
# ==========================================
class HealthCheckFreqCreate(BaseModel):
    patrol: Optional[int] = 60
    diagnosis: Optional[int] = 1440
    report: Optional[int] = 1
    status: Optional[bool] = True
    tenant_id: Optional[UUID] = None


class HealthCheckFreqUpdate(BaseModel):
    patrol: Optional[int] = None
    diagnosis: Optional[int] = None
    report: Optional[int] = None
    status: Optional[bool] = None
    tenant_id: Optional[UUID] = None


class HealthCheckFreqResponse(BaseModel):
    id: UUID
    patrol: int
    diagnosis: int
    report: int
    status: bool
    tenant_id: UUID

    model_config = ConfigDict(from_attributes=True)


@router.get("/health-check-freqs", response_model=List[HealthCheckFreqResponse])
async def list_health_check_freqs(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(db_manager.get_session),
):
    tenant_id = current_account.tenant_id
    return await HealthCheckFreqService.get_health_check_freqs(session, tenant_id, skip, limit)


@router.post("/health-check-freqs", response_model=HealthCheckFreqResponse)
async def create_health_check_freq(
    freq: HealthCheckFreqCreate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(db_manager.get_session),
):
    tenant_id = current_account.tenant_id
    payload = freq.model_dump(exclude_unset=True)
    payload["tenant_id"] = tenant_id
    return await HealthCheckFreqService.create_health_check_freq(session, payload)


@router.put("/health-check-freqs/{freq_id}", response_model=HealthCheckFreqResponse)
async def update_health_check_freq(
    freq_id: UUID,
    freq: HealthCheckFreqUpdate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(db_manager.get_session),
):
    tenant_id = current_account.tenant_id
    db_freq = await HealthCheckFreqService.get_health_check_freq(session, tenant_id, freq_id)
    if not db_freq:
        raise HTTPException(status_code=404, detail="HealthCheckFreq not found")

    update_data = freq.model_dump(exclude_unset=True)
    if "tenant_id" in update_data and update_data["tenant_id"] != tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id cannot be changed")
    update_data.pop("tenant_id", None)
    return await HealthCheckFreqService.update_health_check_freq(session, db_freq, update_data)


@router.delete("/health-check-freqs/{freq_id}")
async def delete_health_check_freq(
    freq_id: UUID,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(db_manager.get_session),
):
    tenant_id = current_account.tenant_id
    db_freq = await HealthCheckFreqService.get_health_check_freq(session, tenant_id, freq_id)
    if not db_freq:
        raise HTTPException(status_code=404, detail="HealthCheckFreq not found")

    await HealthCheckFreqService.delete_health_check_freq(session, db_freq)
    return {"message": "HealthCheckFreq deleted successfully"}
