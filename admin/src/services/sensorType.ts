import { request } from '@umijs/max';

export type SensorType = {
  id: string;
  name: string;
  battery: number;
  network: number;
  bluetooth: boolean;
  description?: string;
};

export type SensorTypePayload = {
  name: string;
  battery?: number;
  network?: number;
  bluetooth?: boolean;
  description?: string;
};

export async function listSensorTypes(skip = 0, limit = 100) {
  return request<SensorType[]>('/api/v1/sensors/types', {
    method: 'GET',
    params: { skip, limit },
  });
}

export async function getSensorType(id: string) {
  return request<SensorType>(`/api/v1/sensors/types/${id}`, {
    method: 'GET',
  });
}

export async function createSensorType(payload: SensorTypePayload) {
  return request<SensorType>('/api/v1/sensors/types', {
    method: 'POST',
    data: payload,
  });
}

export async function updateSensorType(id: string, payload: Partial<SensorTypePayload>) {
  return request<SensorType>(`/api/v1/sensors/types/${id}`, {
    method: 'PUT',
    data: payload,
  });
}

export async function deleteSensorType(id: string) {
  return request<{ message: string }>(`/api/v1/sensors/types/${id}`, {
    method: 'DELETE',
  });
}
