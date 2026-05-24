"""
Customer related management endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID

from app.services.dependencies import get_session
from app.models.customer import Account as AccountModel
from app.services.customer_service import (
    TenantService,
    TenantSensorService,
    SupplierService,
    AccountService,
    ContactService,
    AreaService,
    LocationService,
    HealthCheckFreqService,
)
from app.utils.auth import get_current_account
from app.utils.response import success
from app.contract.customers import (
    TenantCreate,
    TenantUpdate,
    TenantResponse,
    CurrentTenantUpdate,
    TenantSensorCreate,
    TenantSensorUpdate,
    TenantSensorResponse,
    SupplierCreate,
    SupplierUpdate,
    SupplierResponse,
    PagedCountResponse,
    AccountCreate,
    AccountUpdate,
    AccountResponse,
    TenantAccountCreate,
    AdminAccountCreate,
    AreaCreate,
    AreaUpdate,
    AreaResponse,
    LocationCreate,
    LocationUpdate,
    LocationResponse,
    PagedLocationResponse,
    HealthCheckFreqCreate,
    HealthCheckFreqUpdate,
    HealthCheckFreqResponse,
)

router = APIRouter(tags=["customers"])


# ==========================================
# 1b. Current Tenant (authenticated) - MUST be defined before /tenants/{tenant_id}
# ==========================================


@router.get("/tenants/current")
async def get_current_tenant(
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant = await TenantService.get_tenant(session, current_account.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return success(tenant)


@router.put("/tenants/current")
async def update_current_tenant(
    payload: CurrentTenantUpdate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant = await TenantService.get_tenant(session, current_account.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    update_data = payload.model_dump(exclude_unset=True)
    return success(await TenantService.update_tenant(session, tenant, update_data))


@router.get("/tenants")
async def list_tenants(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    tenants = await TenantService.get_tenants(session, skip, limit)
    return success([TenantResponse.model_validate(t) for t in tenants])


@router.get("/tenants/{tenant_id}")
async def get_tenant(
    tenant_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    tenant = await TenantService.get_tenant(session, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return success(tenant)


@router.post("/tenants")
async def create_tenant(
    tenant: TenantCreate,
    session: AsyncSession = Depends(get_session),
):
    return success(await TenantService.create_tenant(session, tenant.model_dump()))


@router.put("/tenants/{tenant_id}")
async def update_tenant(
    tenant_id: UUID,
    tenant: TenantUpdate,
    session: AsyncSession = Depends(get_session),
):
    db_tenant = await TenantService.get_tenant(session, tenant_id)
    if not db_tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    update_data = tenant.model_dump(exclude_unset=True)
    return success(await TenantService.update_tenant(session, db_tenant, update_data))


@router.delete("/tenants/{tenant_id}")
async def delete_tenant(
    tenant_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    db_tenant = await TenantService.get_tenant(session, tenant_id)
    if not db_tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    await TenantService.delete_tenant(session, db_tenant)
    return success({"message": "Tenant deleted successfully"})


# ==========================================
# 2. TenantSensor
# ==========================================
@router.get("/tenant-sensors")
async def list_tenant_sensors(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    return success(await TenantSensorService.get_tenant_sensors(session, skip, limit))


@router.get("/tenant-sensors/{ts_id}")
async def get_tenant_sensor(
    ts_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    ts = await TenantSensorService.get_tenant_sensor(session, ts_id)
    if not ts:
        raise HTTPException(status_code=404, detail="TenantSensor not found")
    return success(ts)


@router.post("/tenant-sensors")
async def create_tenant_sensor(
    ts: TenantSensorCreate,
    session: AsyncSession = Depends(get_session),
):
    return success(await TenantSensorService.create_tenant_sensor(session, ts.model_dump()))


@router.put("/tenant-sensors/{ts_id}")
async def update_tenant_sensor(
    ts_id: UUID,
    ts: TenantSensorUpdate,
    session: AsyncSession = Depends(get_session),
):
    db_ts = await TenantSensorService.get_tenant_sensor(session, ts_id)
    if not db_ts:
        raise HTTPException(status_code=404, detail="TenantSensor not found")

    update_data = ts.model_dump(exclude_unset=True)
    return success(await TenantSensorService.update_tenant_sensor(session, db_ts, update_data))


@router.delete("/tenant-sensors/{ts_id}")
async def delete_tenant_sensor(
    ts_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    db_ts = await TenantSensorService.get_tenant_sensor(session, ts_id)
    if not db_ts:
        raise HTTPException(status_code=404, detail="TenantSensor not found")

    await TenantSensorService.delete_tenant_sensor(session, db_ts)
    return success({"message": "TenantSensor deleted successfully"})


# ==========================================
# 3. Supplier
# ==========================================
@router.get("/suppliers")
async def list_suppliers(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    keyword: Optional[str] = Query(None),
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = current_account.tenant_id
    suppliers = await SupplierService.get_suppliers(session, tenant_id, skip, limit, keyword)
    return success([SupplierResponse.model_validate(s) for s in suppliers])


@router.get("/suppliers/count")
async def count_suppliers(
    keyword: Optional[str] = Query(None),
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = current_account.tenant_id
    total = await SupplierService.count_suppliers(session, tenant_id, keyword)
    return success({"total": total})


@router.get("/suppliers/{supplier_id}")
async def get_supplier(
    supplier_id: UUID,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = current_account.tenant_id
    supplier = await SupplierService.get_supplier(session, tenant_id, supplier_id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return success(supplier)


@router.post("/suppliers")
async def create_supplier(
    supplier: SupplierCreate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = current_account.tenant_id
    payload = supplier.model_dump(exclude_unset=True)
    if "tenant_id" in payload and payload["tenant_id"] is not None and payload["tenant_id"] != tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id mismatch")
    payload["tenant_id"] = tenant_id
    return success(await SupplierService.create_supplier(session, payload))


@router.put("/suppliers/{supplier_id}")
async def update_supplier(
    supplier_id: UUID,
    supplier: SupplierUpdate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = current_account.tenant_id
    db_supplier = await SupplierService.get_supplier(session, tenant_id, supplier_id)
    if not db_supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    update_data = supplier.model_dump(exclude_unset=True)
    return success(await SupplierService.update_supplier(session, db_supplier, update_data))


@router.delete("/suppliers/{supplier_id}")
async def delete_supplier(
    supplier_id: UUID,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = current_account.tenant_id
    db_supplier = await SupplierService.get_supplier(session, tenant_id, supplier_id)
    if not db_supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    await SupplierService.delete_supplier(session, db_supplier)
    return success({"message": "Supplier deleted successfully"})


# ==========================================
# 4b. Tenant-scoped Account (authenticated) - MUST be defined before /accounts/{account_id}
# ==========================================
@router.get("/accounts/by-admin")
async def list_admin_accounts(
    session: AsyncSession = Depends(get_session),
):
    """List all admin accounts (admin=True)"""
    accounts = await AccountService.get_admin_accounts(session)
    contact_ids = [a.contact_id for a in accounts if a.contact_id]
    contact_map = await AccountService.get_contacts_by_ids(session, contact_ids)

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
    return success(response)


@router.post("/accounts/by-admin")
async def create_admin_account(
    payload: AdminAccountCreate,
    session: AsyncSession = Depends(get_session),
):
    """Create a new admin account (admin=True)"""
    import re

    # 判断 username 是邮箱还是手机号，逻辑与 portal 一致
    username = payload.username.strip()
    is_email = re.match(r'^[^@]+@[^@]+\.[^@]+$', username)
    flag = 1 if is_email else 2

    # 1. 先创建 Contact
    contact_data = {
        "name": payload.contact_name,
    }
    if is_email:
        contact_data["email"] = username
    else:
        contact_data["mobile"] = username
    contact = await ContactService.create_contact(session, contact_data)

    # 2. 再创建 Account，关联 contact_id，设置 admin=True
    data = {
        "username": username,
        "password": payload.password,
        "flag": flag,
        "active": True,
        "contact_id": contact.id,
        "admin": True,
    }
    account = await AccountService.create_account(session, data)

    # 3. 返回完整响应
    return success(AccountResponse(
        id=account.id,
        username=account.username,
        flag=account.flag,
        active=account.active,
        admin=account.admin,
        contact_id=account.contact_id,
        contact_name=contact.name,
        tenant_id=account.tenant_id,
    ))


@router.put("/accounts/by-admin/{account_id}")
async def update_admin_account(
    account_id: UUID,
    payload: AccountUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update an admin account"""
    db_account = await AccountService.get_admin_account(session, account_id)
    if not db_account:
        raise HTTPException(status_code=404, detail="Account not found")

    update_data = payload.model_dump(exclude_unset=True)
    update_data.pop("tenant_id", None)
    return success(await AccountService.update_account(session, db_account, update_data))


@router.put("/accounts/by-admin/{account_id}/password")
async def update_admin_account_password(
    account_id: UUID,
    payload: AccountUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update password for an admin account"""
    db_account = await AccountService.get_admin_account(session, account_id)
    if not db_account:
        raise HTTPException(status_code=404, detail="Account not found")

    update_data = payload.model_dump(exclude_unset=True)
    if "password" not in update_data or not update_data["password"]:
        raise HTTPException(status_code=400, detail="Password is required")

    return success(await AccountService.update_account(session, db_account, update_data))


@router.delete("/accounts/by-admin/{account_id}")
async def delete_admin_account(
    account_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """Delete an admin account"""
    db_account = await AccountService.get_admin_account(session, account_id)
    if not db_account:
        raise HTTPException(status_code=404, detail="Account not found")

    await AccountService.delete_account(session, db_account)
    return success({"message": "Account deleted successfully"})


# ==========================================
# 4c. Tenant-scoped Account (authenticated) - for portal
# ==========================================
@router.get("/accounts/by-tenant")
async def list_tenant_accounts(
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    """List all accounts belonging to the current tenant"""
    accounts = await AccountService.get_tenant_accounts(session, current_account.tenant_id)
    contact_ids = [a.contact_id for a in accounts if a.contact_id]
    contact_map = await AccountService.get_contacts_by_ids(session, contact_ids)

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
    return success(response)


@router.post("/accounts/by-tenant")
async def create_tenant_account(
    payload: TenantAccountCreate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    """Create a new account under the current tenant"""
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
    return success(AccountResponse(
        id=account.id,
        username=account.username,
        flag=account.flag,
        active=account.active,
        admin=account.admin,
        contact_id=account.contact_id,
        contact_name=contact.name,
        tenant_id=account.tenant_id,
    ))


@router.put("/accounts/by-tenant/{account_id}")
async def update_tenant_account(
    account_id: UUID,
    payload: AccountUpdate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    """Update an account belonging to the current tenant (e.g. toggle active)"""
    db_account = await AccountService.get_tenant_account(session, account_id, current_account.tenant_id)
    if not db_account:
        raise HTTPException(status_code=404, detail="Account not found")

    update_data = payload.model_dump(exclude_unset=True)
    # 不允许通过此接口修改 tenant_id
    update_data.pop("tenant_id", None)
    return success(await AccountService.update_account(session, db_account, update_data))


@router.put("/accounts/by-tenant/{account_id}/password")
async def update_tenant_account_password(
    account_id: UUID,
    payload: AccountUpdate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    """Update password for an account belonging to the current tenant"""
    db_account = await AccountService.get_tenant_account(session, account_id, current_account.tenant_id)
    if not db_account:
        raise HTTPException(status_code=404, detail="Account not found")

    update_data = payload.model_dump(exclude_unset=True)
    if "password" not in update_data or not update_data["password"]:
        raise HTTPException(status_code=400, detail="Password is required")

    return success(await AccountService.update_account(session, db_account, update_data))


@router.delete("/accounts/by-tenant/{account_id}")
async def delete_tenant_account(
    account_id: UUID,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    """Delete an account belonging to the current tenant"""
    db_account = await AccountService.get_tenant_account(session, account_id, current_account.tenant_id)
    if not db_account:
        raise HTTPException(status_code=404, detail="Account not found")

    await AccountService.delete_account(session, db_account)
    return success({"message": "Account deleted successfully"})


@router.get("/accounts")
async def list_accounts(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    return success(await AccountService.get_accounts(session, skip, limit))


@router.get("/accounts/{account_id}")
async def get_account(
    account_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    account = await AccountService.get_account(session, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return success(account)


@router.post("/accounts")
async def create_account(
    account: AccountCreate,
    session: AsyncSession = Depends(get_session),
):
    # 在实际应用中, 此处通常需对 password 进行哈希处理
    return success(await AccountService.create_account(session, account.model_dump()))


@router.put("/accounts/{account_id}")
async def update_account(
    account_id: UUID,
    account: AccountUpdate,
    session: AsyncSession = Depends(get_session),
):
    db_account = await AccountService.get_account(session, account_id)
    if not db_account:
        raise HTTPException(status_code=404, detail="Account not found")

    update_data = account.model_dump(exclude_unset=True)
    # 实际项目中如果修改 password，也需重新哈希处理
    return success(await AccountService.update_account(session, db_account, update_data))


@router.delete("/accounts/{account_id}")
async def delete_account(
    account_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    db_account = await AccountService.get_account(session, account_id)
    if not db_account:
        raise HTTPException(status_code=404, detail="Account not found")

    await AccountService.delete_account(session, db_account)
    return success({"message": "Account deleted successfully"})


# ==========================================
# 5. Area
# ==========================================
@router.get("/areas")
async def list_areas(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = current_account.tenant_id
    return success(await AreaService.get_areas(session, tenant_id, skip, limit))


@router.post("/areas")
async def create_area(
    area: AreaCreate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = current_account.tenant_id
    payload = area.model_dump(exclude_unset=True)
    if "tenant_id" in payload and payload["tenant_id"] is not None and payload["tenant_id"] != tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id mismatch")
    payload["tenant_id"] = tenant_id
    return success(await AreaService.create_area(session, payload))


@router.put("/areas/{area_id}")
async def update_area(
    area_id: UUID,
    area: AreaUpdate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = current_account.tenant_id
    db_area = await AreaService.get_area(session, tenant_id, area_id)
    if not db_area:
        raise HTTPException(status_code=404, detail="Area not found")

    update_data = area.model_dump(exclude_unset=True)
    if "tenant_id" in update_data and update_data["tenant_id"] != tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id cannot be changed")
    update_data.pop("tenant_id", None)
    return success(await AreaService.update_area(session, db_area, update_data))


@router.delete("/areas/{area_id}")
async def delete_area(
    area_id: UUID,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = current_account.tenant_id
    db_area = await AreaService.get_area(session, tenant_id, area_id)
    if not db_area:
        raise HTTPException(status_code=404, detail="Area not found")

    await AreaService.delete_area(session, db_area)
    return success({"message": "Area deleted successfully"})


# ==========================================
# 6. Location
# ==========================================
@router.get("/locations")
async def list_locations(
    current: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    keyword: Optional[str] = Query(None),
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = current_account.tenant_id
    items, total = await LocationService.get_paged_locations(
        session, tenant_id, current, pageSize, keyword
    )
    return success(PagedLocationResponse(items=items, total=total))


@router.post("/locations")
async def create_location(
    location: LocationCreate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = current_account.tenant_id
    payload = location.model_dump(exclude_unset=True)
    if "tenant_id" in payload and payload["tenant_id"] is not None and payload["tenant_id"] != tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id mismatch")
    payload["tenant_id"] = tenant_id
    return success(await LocationService.create_location(session, payload))


@router.put("/locations/{location_id}")
async def update_location(
    location_id: UUID,
    location: LocationUpdate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = current_account.tenant_id
    db_obj = await LocationService.get_location(session, tenant_id, location_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Location not found")

    update_data = location.model_dump(exclude_unset=True)
    if "tenant_id" in update_data and update_data["tenant_id"] != tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id cannot be changed")
    update_data.pop("tenant_id", None)
    return success(await LocationService.update_location(session, db_obj, update_data))


@router.delete("/locations/{location_id}")
async def delete_location(
    location_id: UUID,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = current_account.tenant_id
    db_obj = await LocationService.get_location(session, tenant_id, location_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Location not found")

    await LocationService.delete_location(session, db_obj)
    return success({"message": "Location deleted successfully"})


# ==========================================
# 7. HealthCheckFreq
# ==========================================
@router.get("/health-check-freqs")
async def list_health_check_freqs(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = current_account.tenant_id
    return success(await HealthCheckFreqService.get_health_check_freqs(session, tenant_id, skip, limit))


@router.post("/health-check-freqs")
async def create_health_check_freq(
    freq: HealthCheckFreqCreate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = current_account.tenant_id
    payload = freq.model_dump(exclude_unset=True)
    payload["tenant_id"] = tenant_id
    return success(await HealthCheckFreqService.create_health_check_freq(session, payload))


@router.put("/health-check-freqs/{freq_id}")
async def update_health_check_freq(
    freq_id: UUID,
    freq: HealthCheckFreqUpdate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = current_account.tenant_id
    db_freq = await HealthCheckFreqService.get_health_check_freq(session, tenant_id, freq_id)
    if not db_freq:
        raise HTTPException(status_code=404, detail="HealthCheckFreq not found")

    update_data = freq.model_dump(exclude_unset=True)
    if "tenant_id" in update_data and update_data["tenant_id"] != tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id cannot be changed")
    update_data.pop("tenant_id", None)
    return success(await HealthCheckFreqService.update_health_check_freq(session, db_freq, update_data))


@router.delete("/health-check-freqs/{freq_id}")
async def delete_health_check_freq(
    freq_id: UUID,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = current_account.tenant_id
    db_freq = await HealthCheckFreqService.get_health_check_freq(session, tenant_id, freq_id)
    if not db_freq:
        raise HTTPException(status_code=404, detail="HealthCheckFreq not found")

    await HealthCheckFreqService.delete_health_check_freq(session, db_freq)
    return success({"message": "HealthCheckFreq deleted successfully"})
