import { request } from '@umijs/max';
import {
  requestAllListItems,
  requestPagedList,
  type PagedResult,
  type SortParams,
} from '@/utils/proTableRequest';

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
  color?: string | null;
  parent_id?: string | null;
  parent?: { id: string; name: string } | null;
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
  color?: string | null;
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
  name?: string;
  description?: string;
  color?: string;
  parent_id?: string;
  health_check_freq_id?: string;
  iso_standard_id?: string;
  vib_threshold_id?: string;
  temp_threshold_id?: string;
};

export type DeviceCategoryPagedResult = PagedResult<DeviceCategory>;

export async function listDeviceCategories() {
  return requestAllListItems<DeviceCategory>('/api/v1/device-categories');
}

export async function listAllDeviceCategories() {
  return requestAllListItems<DeviceCategory>('/api/v1/device-categories');
}

export async function queryDeviceCategories(
  params: DeviceCategoryQueryParams = {},
  sort: SortParams = {},
): Promise<DeviceCategoryPagedResult> {
  return requestPagedList<DeviceCategory>('/api/v1/device-categories', {
    params,
    sort,
    defaultPageSize: 20,
  });
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
  return requestAllListItems<HealthCheckFreq>('/api/v1/health-check-freqs');
}

export async function listIsoStandards() {
  return requestAllListItems<IsoStandard>('/api/v1/iso-standards');
}
