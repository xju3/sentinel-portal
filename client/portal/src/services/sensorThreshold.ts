import { request } from '@umijs/max';
import { requestAllListItems, requestPagedList, type SortParams } from '@/utils/proTableRequest';

export type SensorThreshold = {
  id: string;
  code: string;
  metric: number;
  rt_max_delta: number;
  st_max_slope: number;
  st_max_amplitude: number;
  mt_max_slope: number;
  mt_max_amplitude: number;
  baseline: number;
  tenant_id: string;
};

export type SensorThresholdPayload = {
  code: string;
  metric: number;
  rt_max_delta: number;
  st_max_slope: number;
  st_max_amplitude: number;
  mt_max_slope: number;
  mt_max_amplitude: number;
  baseline: number;
};

export async function listSensorThresholds() {
  return requestAllListItems<SensorThreshold>('/api/v1/thresholds', {}, 200);
}

export async function querySensorThresholds(
  params: Record<string, any> = {},
  sort: SortParams = {},
) {
  return requestPagedList<SensorThreshold>('/api/v1/thresholds', {
    params,
    sort,
    defaultPageSize: 20,
  });
}

export async function createSensorThreshold(payload: SensorThresholdPayload) {
  return request<SensorThreshold>('/api/v1/thresholds', {
    method: 'POST',
    data: payload,
  });
}

export async function updateSensorThreshold(
  id: string,
  payload: Partial<SensorThresholdPayload>,
) {
  return request<SensorThreshold>(`/api/v1/thresholds/${id}`, {
    method: 'PUT',
    data: payload,
  });
}

export async function deleteSensorThreshold(id: string) {
  return request<{ message: string }>(`/api/v1/thresholds/${id}`, {
    method: 'DELETE',
  });
}
