"""
Organization management endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import cast, List, Optional
from uuid import UUID

from pub.services import get_session
from pub.services.customer.org_service import DepartmentService, EmployeeService
from app.utils.auth import get_current_account
from pub.models.customer import Account as AccountModel
from app.utils.response import success

from pub.contract.org import (
    DepartmentCreate,
    DepartmentUpdate,
    DepartmentResponse,
    DepartmentMembersUpdate,
    EmployeeCreate,
    EmployeeUpdate,
    EmployeeResponse,
)

router = APIRouter(tags=["organization"])

# ==========================================
# Departments
# ==========================================
@router.get("/departments")
async def list_departments(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    sort_by: Optional[str] = None,
    sort_order: str = Query("ascend", pattern="^(ascend|descend)$"),
    session: AsyncSession = Depends(get_session),
    current_account: AccountModel = Depends(get_current_account),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    departments = await DepartmentService.get_departments(session, tenant_id, skip, limit, sort_by, sort_order)
    
    # We might want to populate leader_name manually for simplicity if we don't join
    # but for now we'll just return the schema
    results = []
    for d in departments:
        resp = DepartmentResponse.model_validate(d)
        if d.leader:
            resp.leader_name = d.leader.name
        results.append(resp)
    
    return success(results)

@router.get("/departments/{dept_id}")
async def get_department(
    dept_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_account: AccountModel = Depends(get_current_account),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    dept = await DepartmentService.get_department(session, dept_id)
    if not dept or dept.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Department not found")
    
    resp = DepartmentResponse.model_validate(dept)
    if dept.leader:
        resp.leader_name = dept.leader.name
    return success(resp)

@router.post("/departments")
async def create_department(
    department: DepartmentCreate,
    session: AsyncSession = Depends(get_session),
    current_account: AccountModel = Depends(get_current_account),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    data = department.model_dump()
    data["tenant_id"] = tenant_id
    dept = await DepartmentService.create_department(session, data)
    return success(DepartmentResponse.model_validate(dept))

@router.put("/departments/{dept_id}")
async def update_department(
    dept_id: UUID,
    department: DepartmentUpdate,
    session: AsyncSession = Depends(get_session),
    current_account: AccountModel = Depends(get_current_account),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    db_dept = await DepartmentService.get_department(session, dept_id)
    if not db_dept or db_dept.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Department not found")
    
    update_data = department.model_dump(exclude_unset=True)
    dept = await DepartmentService.update_department(session, db_dept, update_data)
    return success(DepartmentResponse.model_validate(dept))

@router.post("/departments/{dept_id}/members")
async def update_department_members_api(
    dept_id: UUID,
    members: DepartmentMembersUpdate,
    session: AsyncSession = Depends(get_session),
    current_account: AccountModel = Depends(get_current_account),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    db_dept = await DepartmentService.get_department(session, dept_id)
    if not db_dept or db_dept.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Department not found")
    
    await DepartmentService.update_department_members(session, dept_id, tenant_id, members.employee_ids)
    
    # Leader might have been removed, but let's assume the admin knows what they are doing.
    # Alternatively we could re-run _ensure_leader_in_department.
    await DepartmentService._ensure_leader_in_department(session, db_dept)
    await session.commit()
    
    return success({"message": "Department members updated successfully"})

@router.delete("/departments/{dept_id}")
async def delete_department(
    dept_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_account: AccountModel = Depends(get_current_account),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    db_dept = await DepartmentService.get_department(session, dept_id)
    if not db_dept or db_dept.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Department not found")
    
    await DepartmentService.delete_department(session, db_dept)
    return success({"message": "Department deleted successfully"})

# ==========================================
# Employees
# ==========================================
@router.get("/employees")
async def list_employees(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    sort_by: Optional[str] = None,
    sort_order: str = Query("ascend", pattern="^(ascend|descend)$"),
    has_wx_user_id: Optional[bool] = None,
    session: AsyncSession = Depends(get_session),
    current_account: AccountModel = Depends(get_current_account),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    employees = await EmployeeService.get_employees(session, tenant_id, skip, limit, sort_by, sort_order, has_wx_user_id)
    results = []
    for e in employees:
        resp = EmployeeResponse.model_validate(e)
        resp.department_ids = [d.id for d in e.departments]
        results.append(resp)
    return success(results)

@router.get("/employees/{emp_id}")
async def get_employee(
    emp_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_account: AccountModel = Depends(get_current_account),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    emp = await EmployeeService.get_employee(session, emp_id)
    if not emp or emp.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    resp = EmployeeResponse.model_validate(emp)
    resp.department_ids = [d.id for d in emp.departments]
    return success(resp)

@router.post("/employees")
async def create_employee(
    employee: EmployeeCreate,
    session: AsyncSession = Depends(get_session),
    current_account: AccountModel = Depends(get_current_account),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    data = employee.model_dump(exclude={"department_ids"})
    data["tenant_id"] = tenant_id
    emp = await EmployeeService.create_employee(session, data, employee.department_ids)
    
    resp = EmployeeResponse.model_validate(emp)
    resp.department_ids = employee.department_ids
    return success(resp)

@router.put("/employees/{emp_id}")
async def update_employee(
    emp_id: UUID,
    employee: EmployeeUpdate,
    session: AsyncSession = Depends(get_session),
    current_account: AccountModel = Depends(get_current_account),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    db_emp = await EmployeeService.get_employee(session, emp_id)
    if not db_emp or db_emp.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    data = employee.model_dump(exclude={"department_ids"}, exclude_unset=True)
    emp = await EmployeeService.update_employee(session, db_emp, data, employee.department_ids)
    
    resp = EmployeeResponse.model_validate(emp)
    resp.department_ids = employee.department_ids if employee.department_ids is not None else [d.id for d in emp.departments]
    return success(resp)

@router.delete("/employees/{emp_id}")
async def delete_employee(
    emp_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_account: AccountModel = Depends(get_current_account),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    db_emp = await EmployeeService.get_employee(session, emp_id)
    if not db_emp or db_emp.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    await EmployeeService.delete_employee(session, db_emp)
    return success({"message": "Employee deleted successfully"})

@router.post("/employees/{emp_id}/unbind-wx")
async def unbind_employee_wx(
    emp_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_account: AccountModel = Depends(get_current_account),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    db_emp = await EmployeeService.get_employee(session, emp_id)
    if not db_emp or db_emp.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Employee not found")
        
    if not db_emp.wx_user_id:
        return success({"message": "Employee is not bound to WeChat"})
        
    await EmployeeService.unbind_employee_wx(session, db_emp)
    return success({"message": "WeChat unbound successfully"})
