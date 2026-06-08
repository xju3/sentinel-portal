import { request } from '@umijs/max';

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
  const limit = 100;
  let skip = 0;
  const all: HealthCheckFreq[] = [];

  while (true) {
    const batch =
      (await request<HealthCheckFreq[]>('/api/v1/health-check-freqs', {
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
