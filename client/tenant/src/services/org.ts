import { request } from '@umijs/max';

export interface DepartmentInfo {
  id: string;
  code: string;
  name: string;
  description?: string;
  leader_id?: string;
  leader_name?: string;
  parent_id?: string;
  tenant_id: string;
  active: boolean;
}

export interface EmployeeInfo {
  id: string;
  code: string;
  name: string;
  mobile?: string;
  tenant_id: string;
  active: boolean;
  department_ids?: string[];
}

export async function listDepartments(params?: {
  skip?: number;
  limit?: number;
  sort_by?: string;
  sort_order?: string;
}) {
  return request<DepartmentInfo[]>('/api/v1/departments', {
    method: 'GET',
    params,
  });
}

export async function createDepartment(data: Partial<DepartmentInfo>) {
  return request<DepartmentInfo>('/api/v1/departments', {
    method: 'POST',
    data,
  });
}

export async function updateDepartment(id: string, data: Partial<DepartmentInfo>) {
  return request<DepartmentInfo>(`/api/v1/departments/${id}`, {
    method: 'PUT',
    data,
  });
}

export async function deleteDepartment(id: string) {
  return request(`/api/v1/departments/${id}`, {
    method: 'DELETE',
  });
}

export async function listEmployees(params?: {
  skip?: number;
  limit?: number;
  sort_by?: string;
  sort_order?: string;
}) {
  return request<EmployeeInfo[]>('/api/v1/employees', {
    method: 'GET',
    params,
  });
}

export async function createEmployee(data: Partial<EmployeeInfo>) {
  return request<EmployeeInfo>('/api/v1/employees', {
    method: 'POST',
    data,
  });
}

export async function updateEmployee(id: string, data: Partial<EmployeeInfo>) {
  return request<EmployeeInfo>(`/api/v1/employees/${id}`, {
    method: 'PUT',
    data,
  });
}

export async function deleteEmployee(id: string) {
  return request(`/api/v1/employees/${id}`, {
    method: 'DELETE',
  });
}
