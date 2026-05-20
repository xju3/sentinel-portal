import { request } from '@umijs/max';

export type TenantSensor = {
  id: string;
  tenant_id: string;
  sensor_id: string;
  available: boolean;
};

export type Sensor = {
  id: string;
  sn: string;
  description?: string;
  active: boolean;
  active_at: string;
  created_at: string;
  updated_at: string;
  sensor_type_id: string;
};

export async function listAllTenantSensors() {
  const limit = 100;
  let skip = 0;
  const all: TenantSensor[] = [];

  while (true) {
    const batch =
      (await request<TenantSensor[]>('/api/v1/tenant-sensors', {
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

export type PagedSensorResult = {
  items: Sensor[];
  total: number;
};

export async function listAllSensors() {
  const pageSize = 100;
  let current = 1;
  const all: Sensor[] = [];

  while (true) {
    const result = await request<PagedSensorResult>('/api/v1/sensors', {
      method: 'GET',
      params: { current, pageSize },
    });
    all.push(...result.items);
    if (result.items.length < pageSize) {
      break;
    }
    current++;
  }

  return all;
}

export async function querySensors(
  current: number,
  pageSize: number,
  keyword?: string,
) {
  return request<PagedSensorResult>('/api/v1/sensors', {
    method: 'GET',
    params: { current, pageSize, keyword },
  });
}
