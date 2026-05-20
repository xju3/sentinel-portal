import { request } from '@umijs/max';

// ==========================================
// Tenant
// ==========================================
export type TenantInfo = {
  id: string;
  code: string;
  name: string;
  host: string;
  active: boolean;
};

export type TenantUpdatePayload = {
  name?: string;
  host?: string;
};

export async function getCurrentTenant() {
  return request<TenantInfo>('/api/v1/tenants/current', {
    method: 'GET',
  });
}

export async function updateCurrentTenant(payload: TenantUpdatePayload) {
  return request<TenantInfo>('/api/v1/tenants/current', {
    method: 'PUT',
    data: payload,
  });
}

// ==========================================
// Account
// ==========================================
export type AccountInfo = {
  id: string;
  username: string;
  flag: number;
  active: boolean;
  admin: boolean;
  contact_id?: string | null;
  contact_name?: string | null;
  tenant_id: string;
};

export type AccountCreatePayload = {
  contact_name: string;
  username: string;
  password: string;
  flag?: number;
  active?: boolean;
};

export async function listTenantAccounts() {
  return request<AccountInfo[]>('/api/v1/accounts/by-tenant', {
    method: 'GET',
  });
}

export async function createTenantAccount(payload: AccountCreatePayload) {
  return request<AccountInfo>('/api/v1/accounts/by-tenant', {
    method: 'POST',
    data: payload,
  });
}

export async function updateTenantAccount(accountId: string, payload: { active?: boolean }) {
  return request<AccountInfo>(`/api/v1/accounts/by-tenant/${accountId}`, {
    method: 'PUT',
    data: payload,
  });
}

export async function updateTenantAccountPassword(accountId: string, payload: { password: string }) {
  return request<AccountInfo>(`/api/v1/accounts/by-tenant/${accountId}/password`, {
    method: 'PUT',
    data: payload,
  });
}

export async function deleteTenantAccount(accountId: string) {
  return request(`/api/v1/accounts/by-tenant/${accountId}`, {
    method: 'DELETE',
  });
}
