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

    let cleanData: Record<string, any> | undefined = undefined
    if (data) {
      cleanData = {}
      for (const key in data) {
        if (data[key] !== undefined) {
          cleanData[key] = data[key]
        }
      }
    }
    wx.request({
      url: `${BASE_URL}${path}`,
      method,
      data: cleanData,
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

/** Get a page of devices which have current or historical sensor monitoring. */
export async function getHealthArchiveDevices(token: string, skip = 0, limit = 10) {
  const data = await request<any>(
    '/wx-mini-app/health-archive/devices',
    'GET',
    { skip, limit },
    token,
  )
  if (Array.isArray(data)) {
    return data
  }
  if (Array.isArray(data?.items)) {
    const hasMore = typeof data.hasMore === 'boolean'
      ? data.hasMore
      : (typeof data.total === 'number'
        ? skip + data.items.length < data.total
        : undefined)
    return { items: data.items, hasMore }
  }
  throw new Error('设备列表响应格式错误')
}

/** Get the diagnosis timeline and monitoring points for one device. */
export function getDeviceHealthArchive(
  token: string,
  deviceId: string,
  params: {
    start_at: string
    end_at: string
    interval_hours: number
    location_id?: string
  },
) {
  return request<any>(`/devices/${deviceId}/health-archive`, 'GET', params, token)
}

/** Get temperature and vibration history for one monitoring point. */
export function getDevicePointTrends(
  token: string,
  deviceId: string,
  params: {
    location_id: string
    range_days: number
    window_minutes: number
  },
) {
  return request<any>(`/devices/${deviceId}/point-trends`, 'GET', params, token)
}

/** Get recent FFT captures for one device. */
export function getDeviceFftRecords(token: string, deviceId: string) {
  return request<any[]>(`/devices/${deviceId}/fft-records`, 'GET', undefined, token)
}

/** Get parsed FFT spectrum data for one capture. */
export function getDeviceFftData(token: string, deviceId: string, recordId: string) {
  return request<any>(
    `/devices/${deviceId}/fft-records/${recordId}/data`,
    'GET',
    undefined,
    token,
  )
}

/** Get device categories */
export function getDeviceCategories(token: string) {
  return request<any[]>('/device-categories', 'GET', { skip: 0, limit: 100 }, token)
}

/** Get list of device specs */
export function getDeviceSpecs(token: string, skip = 0, limit = 100, device_category_id?: string) {
  return request<any[]>('/device-specs', 'GET', { skip, limit, device_category_id }, token)
}

/** Get a page of device specs which belong to at least one comparison group. */
export function getGroupedDeviceSpecs(token: string, skip = 0, limit = 100) {
  return request<any[]>(
    '/wx-mini-app/device-specs',
    'GET',
    { skip, limit, sort_by: 'name', sort_order: 'ascend' },
    token,
  )
}

/** Get all device specs which belong to at least one comparison group. */
export async function getAllGroupedDeviceSpecs(token: string) {
  const limit = 100
  let skip = 0
  const all: any[] = []
  while (true) {
    const batch = await getGroupedDeviceSpecs(token, skip, limit)
    const items = Array.isArray(batch) ? batch : ((batch as any)?.items || [])
    all.push(...items)
    if (items.length < limit) break
    skip += limit
  }
  return all
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
