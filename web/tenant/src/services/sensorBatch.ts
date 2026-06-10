import { request } from '@umijs/max';

export type SensorBatch = {
  id: string;
  code: string;
  qty: number;
  sn: number;
  status: number;
  description?: string;
  sensor_type_id: string;
  tenant_id: string;
  created_at: string;
};

export type Sensor = {
  id: string;
  sn: string;
  description?: string;
  active: boolean;
  active_at: string;
  created_at: string;
  updated_at: string;
};

export async function listSensorBatches(skip = 0, limit = 100) {
  return request<SensorBatch[]>('/api/v1/sensors/batches', {
    method: 'GET',
    params: { skip, limit },
  });
}

export async function listSensorsByBatch(batchId: string, skip = 0, limit = 10) {
  return request<Sensor[]>(`/api/v1/sensors/by-batch/${batchId}`, {
    method: 'GET',
    params: { skip, limit },
  });
}
