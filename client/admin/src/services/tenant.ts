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

export type TenantListParams = {
  skip?: number;
  limit?: number;
  active?: boolean;
  code?: string;
  name?: string;
  mqtt_server?: string;
  api_server?: string;
  status?: number;
  email_status?: number;
  industry?: number;
  email?: string;
  region_id?: string;
  sort_by?: string;
  sort_order?: string;
};

export type TenantListResponse = {
  items: Tenant[];
  total: number;
};

const buildTenantListParams = (
  skip = 0,
  limit = 1000,
  query?: TenantListParams | boolean,
): TenantListParams => {
  if (typeof query === 'boolean') {
    return { skip, limit, active: query };
  }
  return { skip, limit, ...(query || {}) };
};

export async function listTenantPage(skip = 0, limit = 20, query?: TenantListParams) {
  return request<TenantListResponse>('/api/v1/tenants', {
    method: 'GET',
    params: buildTenantListParams(skip, limit, query),
  });
}

export async function listTenants(skip = 0, limit = 1000, query?: TenantListParams | boolean) {
  const response = await request<TenantListResponse>('/api/v1/tenants', {
    method: 'GET',
    params: buildTenantListParams(skip, limit, query),
  });
  return response.items;
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
