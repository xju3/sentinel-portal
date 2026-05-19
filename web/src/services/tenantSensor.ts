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
  battery: number;
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

export async function listAllSensors() {
  const limit = 100;
  let skip = 0;
  const all: Sensor[] = [];

  while (true) {
    const batch =
      (await request<Sensor[]>('/api/v1/sensors', {
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
