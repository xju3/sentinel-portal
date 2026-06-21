import { request } from '@umijs/max';

export type Sensor = {
  id: string;
  sn: string;
  description?: string;
  active: boolean;
  sim_id?: string | null;
  sim_card?: {
    id: string;
    number: string;
    ccid: string;
    carrier: string;
    data_plan: string;
    activated_at?: string | null;
    expires_at: string;
    status: number;
  } | null;
  active_at: string;
  created_at: string;
  updated_at: string;
  sensor_type_id?: string;
  latest_status?: {
    temperature?: number | null;
    battery?: number | null;
    rssi?: number | null;
    ts?: string;
  } | null;
};

export type SensorPayload = {
  sn: string;
  description?: string;
  active?: boolean;
  sim_id?: string | null;
  sensor_type_id?: string;
};

export type PagedSensorResponse = {
  items: Sensor[];
  total: number;
};

export async function listSensors(current = 1, pageSize = 100, keyword?: string) {
  return request<PagedSensorResponse>('/api/v1/sensors', {
    method: 'GET',
    params: { current, pageSize, keyword },
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
