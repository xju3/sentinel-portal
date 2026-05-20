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

export type SensorBatchPayload = {
  code: string;
  qty: number;
  sn: number;
  status?: number;
  description?: string;
  sensor_type_id: string;
};

export async function listSensorBatches(skip = 0, limit = 100) {
  return request<SensorBatch[]>('/api/v1/sensors/batches', {
    method: 'GET',
    params: { skip, limit },
  });
}

export async function getSensorBatch(id: string) {
  return request<SensorBatch>(`/api/v1/sensors/batches/${id}`, {
    method: 'GET',
  });
}

export async function createSensorBatch(payload: SensorBatchPayload) {
  return request<SensorBatch>('/api/v1/sensors/batches', {
    method: 'POST',
    data: payload,
  });
}

export async function updateSensorBatch(id: string, payload: Partial<SensorBatchPayload>) {
  return request<SensorBatch>(`/api/v1/sensors/batches/${id}`, {
    method: 'PUT',
    data: payload,
  });
}

export async function deleteSensorBatch(id: string) {
  return request<{ message: string }>(`/api/v1/sensors/batches/${id}`, {
    method: 'DELETE',
  });
}
