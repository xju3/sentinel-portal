import { request } from '@umijs/max';
import { requestAllListItems, requestPagedList, type SortParams } from '@/utils/proTableRequest';

export type HealthCheckFreq = {
  id: string;
  patrol: number;
  diagnosis: number;
  report: number;
  status: boolean;
  tenant_id: string;
};

export type HealthCheckFreqPayload = {
  patrol: number;
  diagnosis: number;
  report: number;
  status: boolean;
};

export async function listAllHealthCheckFreqs() {
  return requestAllListItems<HealthCheckFreq>('/api/v1/health-check-freqs');
}

export async function queryHealthCheckFreqs(
  params: Record<string, any> = {},
  sort: SortParams = {},
) {
  return requestPagedList<HealthCheckFreq>('/api/v1/health-check-freqs', {
    params,
    sort,
    defaultPageSize: 20,
  });
}

export async function createHealthCheckFreq(payload: HealthCheckFreqPayload) {
  return request<HealthCheckFreq>('/api/v1/health-check-freqs', {
    method: 'POST',
    data: payload,
  });
}

export async function updateHealthCheckFreq(
  id: string,
  payload: Partial<HealthCheckFreqPayload>,
) {
  return request<HealthCheckFreq>(`/api/v1/health-check-freqs/${id}`, {
    method: 'PUT',
    data: payload,
  });
}

export async function deleteHealthCheckFreq(id: string) {
  return request<{ message: string }>(`/api/v1/health-check-freqs/${id}`, {
    method: 'DELETE',
  });
}
