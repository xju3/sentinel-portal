import { request } from '@umijs/max';

export type LoginPayload = {
  username: string;
  password: string;
};

export type LoginResult = {
  account_id: string;
  username: string;
  tenant_id: string;
  tenant_name?: string;
  contact_id?: string;
  contact_name?: string;
  flag: number;
};

export type ChangePasswordPayload = {
  account_id: string;
  current_password: string;
  new_password: string;
};

export async function login(payload: LoginPayload) {
  return request<LoginResult>('/api/v1/auth/login', {
    method: 'POST',
    data: payload,
  });
}

export async function changePassword(payload: ChangePasswordPayload) {
  return request('/api/v1/auth/change-password', {
    method: 'POST',
    data: payload,
  });
}
