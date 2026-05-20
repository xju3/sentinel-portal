import { request } from '@umijs/max';

export type LoginPayload = {
  username: string;
  password: string;
};

export type LoginResult = {
  access_token: string;
  token_type: string;
  expires_in: number;
  account_id: string;
  username: string;
  tenant_id: string;
  tenant_name?: string;
  contact_id?: string;
  contact_name?: string;
  flag: number;
};

export async function login(payload: LoginPayload) {
  return request<LoginResult>('/api/v1/auth/login', {
    method: 'POST',
    data: payload,
  });
}
