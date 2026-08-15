// utils/api.ts — Unified HTTP request wrapper

const BASE_URL = 'https://langhu.ai/api/v1'

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
      data,
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
