// utils/api.ts — Unified HTTP request wrapper

const BASE_URL = 'https://api-server.icu/api/v1'

interface ApiResponse<T = any> {
  code: number
  data: T
  message?: string
}

export function request<T = any>(
  path: string,
  method: 'GET' | 'POST' | 'PUT' | 'DELETE' = 'GET',
  data?: Record<string, any>,
  token?: string,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const header: Record<string, string> = {
      'Content-Type': 'application/json',
    }
    if (token) {
      header['Authorization'] = `Bearer ${token}`
    }

    wx.request({
      url: `${BASE_URL}${path}`,
      method,
      data: data
        ? Object.fromEntries(Object.entries(data).filter(([, v]) => v !== undefined))
        : undefined,
      header,
      success(res) {
        const body = res.data as ApiResponse<T>
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(body.data ?? (body as any))
        } else {
          const detail = (res.data as any)?.detail || '请求失败'
          reject(new Error(detail))
        }
      },
      fail(err) {
        reject(new Error(err.errMsg || '网络异常，请检查网络连接'))
      },
    })
  })
}

/** Exchange wx.login code for user status */
export function miniLogin(code: string) {
  return request<{
    registered: boolean
    openid?: string
    access_token?: string
    tenant_name?: string
    contact_name?: string
    account_id?: string
    tenant_id?: string
    expires_in?: number
  }>('/wx-mini-app/login', 'POST', { code })
}

/** Register new tenant */
export function miniLoginWithPassword(payload: {
  username: string
  password: string
  openid: string
  unionid?: string
}) {
  return request<{
    registered: boolean
    access_token: string
    tenant_name?: string
    contact_name?: string
    account_id: string
    tenant_id: string
    expires_in: number
  }>('/wx-mini-app/bind-login', 'POST', payload)
}

/** Register new tenant */
export function miniRegister(payload: {
  company_name: string
  contact_name: string
  phone: string
  email: string
  openid: string
}) {
  return request<{ message: string; account_id: string; tenant_id: string }>(
    '/wx-mini-app/register',
    'POST',
    payload,
  )
}

/** Get health dashboard summary */
export function getDashboardHealth(token: string) {
  return request<any>('/dashboard/health', 'GET', undefined, token)
}

/** Get device categories */
export function getDeviceCategories(token: string) {
  return request<any[]>('/device-categories', 'GET', { skip: 0, limit: 100 }, token)
}

/** Get list of device specs */
export function getDeviceSpecs(token: string, skip = 0, limit = 100, device_category_id?: string) {
  return request<any[]>('/device-specs', 'GET', { skip, limit, device_category_id }, token)
}

/** Get single device spec detail */
export function getDeviceSpec(token: string, id: string) {
  return request<any>(`/device-specs/${id}`, 'GET', undefined, token)
}

/** Get process devices */
export function getProcessDevices(token: string, skip = 0, limit = 100, device_spec_id?: string) {
  return request<any[]>('/process-devices', 'GET', { skip, limit, device_spec_id }, token)
}

/** Get device spec comparison data */
export function getDeviceSpecComparison(
  token: string,
  deviceSpecId: string,
  params: {
    process_device_id?: string
    location_id?: string
    range_days: number
    window_minutes: number
  }
) {
  return request<any>(`/device-specs/${deviceSpecId}/comparison`, 'GET', params as Record<string, any>, token)
}
