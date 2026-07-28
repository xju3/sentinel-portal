import { request } from '@umijs/max';

export type RegisterPayload = {
  company_name: string;
  contact_name: string;
  phone: string;
  email: string;
};

export type RegisterResult = {
  tenant_id: string;
  contact_id: string;
  account_id: string;
  account_username: string;
  login_channel: 'email';
  email_sent: boolean;
};

export async function registerTenant(payload: RegisterPayload) {
  return request<RegisterResult>('/api/v1/auth/register', {
    method: 'POST',
    data: payload,
  });
}
