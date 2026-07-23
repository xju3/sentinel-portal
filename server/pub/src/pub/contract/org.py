from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID

class DepartmentBase(BaseModel):
    code: str = Field(..., max_length=32)
    name: str = Field(..., max_length=64)
    description: Optional[str] = Field(None, max_length=255)
    leader_id: Optional[UUID] = None
    parent_id: Optional[UUID] = None
    active: bool = True

class DepartmentCreate(DepartmentBase):
    pass

class DepartmentUpdate(BaseModel):
    code: Optional[str] = Field(None, max_length=32)
    name: Optional[str] = Field(None, max_length=64)
    description: Optional[str] = Field(None, max_length=255)
    leader_id: Optional[UUID] = None
    parent_id: Optional[UUID] = None
    active: Optional[bool] = None

class DepartmentMembersUpdate(BaseModel):
    employee_ids: List[UUID]

class DepartmentResponse(DepartmentBase):
    id: UUID
    tenant_id: UUID
    leader_name: Optional[str] = None # Filled manually if needed

    class Config:
        from_attributes = True

class EmployeeBase(BaseModel):
    code: str = Field(..., max_length=32)
    name: str = Field(..., max_length=64)
    mobile: Optional[str] = Field(None, max_length=20)
    active: bool = True

class EmployeeCreate(EmployeeBase):
    department_ids: Optional[List[UUID]] = None

class EmployeeUpdate(BaseModel):
    code: Optional[str] = Field(None, max_length=32)
    name: Optional[str] = Field(None, max_length=64)
    mobile: Optional[str] = Field(None, max_length=20)
    active: Optional[bool] = None
    department_ids: Optional[List[UUID]] = None

class EmployeeResponse(EmployeeBase):
    id: UUID
    tenant_id: UUID
    department_ids: Optional[List[UUID]] = None
    wx_user_id: Optional[str] = None

    class Config:
        from_attributes = True
