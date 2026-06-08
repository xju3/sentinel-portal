import { request } from '@umijs/max';

export type Account = {
  id: string;
  username: string;
  flag: number;
  active: boolean;
  admin: boolean;
  contact_id?: string;
  contact_name?: string;
  tenant_id: string;
};

export type AccountPayload = {
  contact_name: string;
  username: string;
  password: string;
};

export type AccountUpdatePayload = {
  username?: string;
  password?: string;
  flag?: number;
  active?: boolean;
  contact_id?: string;
};

export async function listAccounts() {
  return request<Account[]>('/api/v1/accounts/by-admin', {
    method: 'GET',
  });
}

export async function createAccount(payload: AccountPayload) {
  return request<Account>('/api/v1/accounts/by-admin', {
    method: 'POST',
    data: payload,
  });
}

export async function updateAccount(id: string, payload: AccountUpdatePayload) {
  return request<Account>(`/api/v1/accounts/by-admin/${id}`, {
    method: 'PUT',
    data: payload,
  });
}

export async function updateAccountPassword(id: string, password: string) {
  return request<Account>(`/api/v1/accounts/by-admin/${id}/password`, {
    method: 'PUT',
    data: { password },
  });
}

export async function deleteAccount(id: string) {
  return request<{ message: string }>(`/api/v1/accounts/by-admin/${id}`, {
    method: 'DELETE',
  });
}
