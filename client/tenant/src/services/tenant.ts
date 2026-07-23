import { request } from '@umijs/max';

// ==========================================
// Tenant
// ==========================================
export type TenantInfo = {
  id: string;
  code: string;
  name: string;
  mqtt_server: string;
  api_server: string;
  active: boolean;
};

export type TenantUpdatePayload = {
  name?: string;
  mqtt_server?: string;
  api_server?: string;
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
  wx_user_id?: string | null;
  email?: string | null;
  mobile?: string | null;
  employee_id?: string | null;
};

export type TenantAccountCreatePayload = {
  username: string;
  password?: string;
  flag: number;
  active?: boolean;
  contact_name?: string;
  email?: string;
  mobile?: string;
  employee_id?: string;
};

export async function listTenantAccounts() {
  return request<AccountInfo[]>('/api/v1/accounts/by-tenant', {
    method: 'GET',
  });
}

export async function createTenantAccount(payload: TenantAccountCreatePayload) {
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

export async function getWxBindQrCode(accountId: string) {
  return request<{ data: { ticket: string; scene_str: string; qr_url: string } }>('/api/v1/wx/bind-qrcode', {
    method: 'GET',
    params: { target_account_id: accountId },
  });
}

export async function checkWxBindStatus(sceneStr: string) {
  return request<{ code: number; message: string }>('/api/v1/wx/bind-status', {
    method: 'GET',
    params: { scene_str: sceneStr },
    skipErrorHandler: true,
  });
}

export async function unbindTenantAccountWx(accountId: string) {
  return request(`/api/v1/accounts/by-tenant/${accountId}/unbind-wx`, {
    method: 'POST',
  });
}
