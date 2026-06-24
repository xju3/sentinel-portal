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

export type ChangePasswordPayload = {
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

export async function getWxLoginQrCode() {
  return request<{ data: { ticket: string; scene_str: string; qr_url: string } }>('/api/v1/wx/login-qrcode', {
    method: 'GET',
  });
}

export async function checkWxLoginStatus(sceneStr: string) {
  // Returns LoginResult on success (200), or code: 202 if waiting, or code: 404 if not bound.
  // Note: Unbound case returns HTTP 404, so it might throw an error.
  return request<{ code?: number; data?: LoginResult; message?: string }>('/api/v1/wx/login-status', {
    method: 'GET',
    params: { scene_str: sceneStr },
  });
}
