import { request } from '@umijs/max';

export type Tenant = {
  id: string;
  code: string;
  name: string;
  mqtt_server: string;
  api_server: string;
  region_id: string;
  active: boolean;
  status?: number;
  industry?: number;
  email?: string;
  email_status?: number;
  remark?: string;
};

export type TenantPayload = {
  code: string;
  name: string;
  mqtt_server: string;
  api_server: string;
  region_id: string;
  active?: boolean;
  status?: number;
  industry?: number;
  email?: string;
  remark?: string;
};

export async function listTenants(skip = 0, limit = 1000, active?: boolean) {
  return request<Tenant[]>('/api/v1/tenants', {
    method: 'GET',
    params: { skip, limit, ...(active !== undefined ? { active } : {}) },
  });
}

export async function getTenant(id: string) {
  return request<Tenant>(`/api/v1/tenants/${id}`, {
    method: 'GET',
  });
}

export async function createTenant(payload: TenantPayload) {
  return request<Tenant>('/api/v1/tenants', {
    method: 'POST',
    data: payload,
  });
}

export async function updateTenant(id: string, payload: Partial<TenantPayload>) {
  return request<Tenant>(`/api/v1/tenants/${id}`, {
    method: 'PUT',
    data: payload,
  });
}

export async function deleteTenant(id: string) {
  return request<{ message: string }>(`/api/v1/tenants/${id}`, {
    method: 'DELETE',
  });
}
