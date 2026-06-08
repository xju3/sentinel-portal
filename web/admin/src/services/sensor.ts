import { request } from '@umijs/max';

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

export type SensorPayload = {
  sn: string;
  description?: string;
  active?: boolean;
  sensor_type_id: string;
};

export type PagedSensorResponse = {
  items: Sensor[];
  total: number;
};

export async function listSensors(current = 1, pageSize = 100) {
  return request<PagedSensorResponse>('/api/v1/sensors', {
    method: 'GET',
    params: { current, pageSize },
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
