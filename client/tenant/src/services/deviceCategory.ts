import { request } from '@umijs/max';

export type HealthCheckFreqRef = {
  id: string;
  patrol: number;
  diagnosis: number;
  report: number;
  status: boolean;
};

export type DeviceCategory = {
  id: string;
  name: string;
  description?: string;
  parent_id?: string | null;
  health_check_freq_id: string;
  tenant_id?: string | null;
  iso_standard_id?: string | null;
  vib_threshold_id?: string | null;
  temp_threshold_id?: string | null;
  health_check_freq?: HealthCheckFreqRef | null;
  iso_standard?: { id: string; code: string; version: number } | null;
  vib_threshold?: { id: string; code: string } | null;
  temp_threshold?: { id: string; code: string } | null;
  employees?: { id: string; name: string }[] | null;
};

export type DeviceCategoryPayload = {
  name: string;
  description?: string;
  parent_id?: string | null;
  health_check_freq_id: string;
  iso_standard_id?: string | null;
  vib_threshold_id?: string | null;
  temp_threshold_id?: string | null;
};

export type HealthCheckFreq = {
  id: string;
  patrol: number;
  diagnosis: number;
  report: number;
  status: boolean;
  tenant_id: string;
};

export type IsoStandard = {
  id: string;
  code: string;
  version: number;
  category: number;
  foundation: number;
  description?: string;
};

export type DeviceCategoryQueryParams = {
  current?: number;
  pageSize?: number;
  keyword?: string;
};

export type DeviceCategoryPagedResult = {
  items: DeviceCategory[];
  total: number;
};

export async function listDeviceCategories() {
  return request<DeviceCategory[]>('/api/v1/device-categories', {
    method: 'GET',
    params: { skip: 0, limit: 100 },
  });
}

export async function listAllDeviceCategories() {
  const limit = 100;
  let skip = 0;
  const all: DeviceCategory[] = [];

  while (true) {
    const batch =
      (await request<DeviceCategory[]>('/api/v1/device-categories', {
        method: 'GET',
        params: { skip, limit },
      })) || [];
    all.push(...batch);
    if (batch.length < limit) {
      break;
    }
    skip += limit;
  }

  return all;
}

export async function queryDeviceCategories(
  params: DeviceCategoryQueryParams = {},
): Promise<DeviceCategoryPagedResult> {
  const current = params.current || 1;
  const pageSize = params.pageSize || 10;
  const skip = (current - 1) * pageSize;
  const list =
    (await request<DeviceCategory[]>('/api/v1/device-categories', {
      method: 'GET',
      params: {
        skip,
        limit: pageSize,
        keyword: params.keyword || undefined,
      },
    })) || [];

  const countRes = await request<{ total: number }>('/api/v1/device-categories/count', {
    method: 'GET',
    params: {
      keyword: params.keyword || undefined,
    },
  });

  return {
    items: list,
    total: countRes?.total || 0,
  };
}

export async function createDeviceCategory(payload: DeviceCategoryPayload) {
  return request<DeviceCategory>('/api/v1/device-categories', {
    method: 'POST',
    data: payload,
  });
}

export async function updateDeviceCategory(id: string, payload: Partial<DeviceCategoryPayload>) {
  return request<DeviceCategory>(`/api/v1/device-categories/${id}`, {
    method: 'PUT',
    data: payload,
  });
}

export async function deleteDeviceCategory(id: string) {
  return request<{ message: string }>(`/api/v1/device-categories/${id}`, {
    method: 'DELETE',
  });
}

export async function updateDeviceCategoryEmployees(id: string, employee_ids: string[]) {
  return request(`/api/v1/device-categories/${id}/employees`, {
    method: 'POST',
    data: { employee_ids },
  });
}

export async function listHealthCheckFreqs() {
  return request<HealthCheckFreq[]>('/api/v1/health-check-freqs', {
    method: 'GET',
    params: { skip: 0, limit: 100 },
  });
}

export async function listIsoStandards() {
  return request<IsoStandard[]>('/api/v1/iso-standards', {
    method: 'GET',
    params: { skip: 0, limit: 100 },
  });
}
