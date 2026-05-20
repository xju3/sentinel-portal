import { request } from '@umijs/max';

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

export type SensorPayload = {
  sn: string;
  description?: string;
  battery?: number;
  active?: boolean;
  sensor_type_id: string;
};

export async function listSensors(skip = 0, limit = 100) {
  return request<Sensor[]>('/api/v1/sensors', {
    method: 'GET',
    params: { skip, limit },
  });
}

export async function getSensor(id: string) {
  return request<Sensor>(`/api/v1/sensors/${id}`, {
    method: 'GET',
  });
}

export async function createSensor(payload: SensorPayload) {
  return request<Sensor>('/api/v1/sensors', {
    method: 'POST',
    data: payload,
  });
}

export async function updateSensor(id: string, payload: Partial<SensorPayload>) {
  return request<Sensor>(`/api/v1/sensors/${id}`, {
    method: 'PUT',
    data: payload,
  });
}

export async function deleteSensor(id: string) {
  return request<{ message: string }>(`/api/v1/sensors/${id}`, {
    method: 'DELETE',
  });
}
