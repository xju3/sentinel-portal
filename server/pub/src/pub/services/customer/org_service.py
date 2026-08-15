"""
Organization service - business logic for departments and employees
"""

from uuid import UUID
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import func, delete

from pub.models.org import Department, Employee, EmployeeDepartment
from pub.utils.sorting import apply_sorting

class DepartmentService:
    @staticmethod
    async def get_departments(
        session: AsyncSession,
        tenant_id: UUID,
        skip: int = 0,
        limit: int = 100,
        sort_by: str | None = None,
        sort_order: str = "ascend",
    ) -> List[Department]:
        stmt = select(Department).options(selectinload(Department.leader)).where(Department.tenant_id == tenant_id, Department.active == True)
        stmt = apply_sorting(stmt, Department, sort_by, sort_order)
        stmt = stmt.offset(skip).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_department(session: AsyncSession, dept_id: UUID) -> Optional[Department]:
        stmt = select(Department).options(selectinload(Department.leader)).where(Department.id == dept_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def _ensure_leader_in_department(session: AsyncSession, dept: Department) -> None:
        if not dept.leader_id:
            return
            
        stmt = select(EmployeeDepartment).where(
            EmployeeDepartment.employee_id == dept.leader_id,
            EmployeeDepartment.department_id == dept.id
        )
        result = await session.execute(stmt)
        if not result.scalars().first():
            session.add(EmployeeDepartment(
                employee_id=dept.leader_id,
                department_id=dept.id,
                tenant_id=dept.tenant_id
            ))

    @staticmethod
    async def create_department(session: AsyncSession, data: dict) -> Department:
        db_dept = Department(**data)
        session.add(db_dept)
        await session.flush()
        
        await DepartmentService._ensure_leader_in_department(session, db_dept)
        
        await session.commit()
        await session.refresh(db_dept)
        return db_dept

    @staticmethod
    async def update_department(session: AsyncSession, db_dept: Department, data: dict) -> Department:
        for key, value in data.items():
            setattr(db_dept, key, value)
            
        await session.flush()
        await DepartmentService._ensure_leader_in_department(session, db_dept)
        
        await session.commit()
        await session.refresh(db_dept)
        return db_dept

    @staticmethod
    async def delete_department(session: AsyncSession, db_dept: Department) -> None:
        await session.delete(db_dept)
        await session.commit()

    @staticmethod
    async def update_department_members(session: AsyncSession, dept_id: UUID, tenant_id: UUID, employee_ids: List[UUID]) -> None:
        # Delete existing members
        await session.execute(
            delete(EmployeeDepartment).where(EmployeeDepartment.department_id == dept_id)
        )
        
        # Add new members
        for emp_id in employee_ids:
            session.add(EmployeeDepartment(
                employee_id=emp_id,
                department_id=dept_id,
                tenant_id=tenant_id
            ))
            
        await session.commit()

class EmployeeService:
    @staticmethod
    async def get_employees(
        session: AsyncSession,
        tenant_id: UUID,
        skip: int = 0,
        limit: int = 100,
        sort_by: str | None = None,
        sort_order: str = "ascend",
        has_wx_user_id: bool | None = None,
    ) -> List[Employee]:
        stmt = select(Employee).options(selectinload(Employee.departments)).where(Employee.tenant_id == tenant_id, Employee.active == True)
        if has_wx_user_id is not None:
            if has_wx_user_id:
                stmt = stmt.where(Employee.wx_user_id.is_not(None))
            else:
                stmt = stmt.where(Employee.wx_user_id.is_(None))
        
        stmt = apply_sorting(stmt, Employee, sort_by, sort_order)
        stmt = stmt.offset(skip).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_employee(session: AsyncSession, employee_id: UUID) -> Optional[Employee]:
        stmt = select(Employee).options(selectinload(Employee.departments)).where(Employee.id == employee_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create_employee(session: AsyncSession, data: dict, department_ids: List[UUID] = None) -> Employee:
        db_emp = Employee(**data)
        session.add(db_emp)
        await session.flush()
        
        if department_ids:
            for dept_id in department_ids:
                session.add(EmployeeDepartment(employee_id=db_emp.id, department_id=dept_id, tenant_id=db_emp.tenant_id))
                
        await session.commit()
        await session.refresh(db_emp)
        return db_emp

    @staticmethod
    async def update_employee(session: AsyncSession, db_emp: Employee, data: dict, department_ids: List[UUID] = None) -> Employee:
        for key, value in data.items():
            setattr(db_emp, key, value)
            
        if department_ids is not None:
            # Delete existing relations
            await session.execute(
                delete(EmployeeDepartment).where(EmployeeDepartment.employee_id == db_emp.id)
            )
            # Add new relations
            for dept_id in department_ids:
                session.add(EmployeeDepartment(employee_id=db_emp.id, department_id=dept_id, tenant_id=db_emp.tenant_id))
                
        await session.commit()
        await session.refresh(db_emp)
        return db_emp

    @staticmethod
    async def delete_employee(session: AsyncSession, db_emp: Employee) -> None:
        await session.delete(db_emp)
        await session.commit()

    @staticmethod
    async def get_employee_by_wx_user_id(
        session: AsyncSession, wx_user_id: str
    ) -> Optional[Employee]:
        stmt = select(Employee).where(Employee.wx_user_id == wx_user_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def bind_employee_wx(
        session: AsyncSession, employee: Employee, wx_user_id: str, wx_union_id: Optional[str] = None
    ) -> None:
        employee.wx_user_id = wx_user_id
        if wx_union_id:
            employee.wx_union_id = wx_union_id
        await session.commit()

    @staticmethod
    async def get_employee_by_wx_union_id(
        session: AsyncSession, wx_union_id: str
    ) -> Optional[Employee]:
        stmt = select(Employee).where(Employee.wx_union_id == wx_union_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def bind_employee_wx_union(
        session: AsyncSession, employee: Employee, wx_union_id: str
    ) -> None:
        employee.wx_union_id = wx_union_id
        await session.commit()

    @staticmethod
    async def unbind_employee_wx(
        session: AsyncSession, employee: Employee
    ) -> None:
        employee.wx_user_id = None
        await session.commit()
