import { request } from '@umijs/max';

export type DeviceSpec = {
  id: string;
  name: string;
  model: string;
  description?: string;
  brand: string;
  voltage: number;
  rpm: number;
  supplier_id: string;
  device_category_id: string;
};

export type DeviceSpecPayload = {
  name: string;
  model: string;
  description?: string;
  brand: string;
  voltage?: number;
  rpm?: number;
  supplier_id: string;
  device_category_id: string;
};

export async function listDeviceSpecs(skip = 0, limit = 100) {
  return request<DeviceSpec[]>('/api/v1/device-specs', {
    method: 'GET',
    params: { skip, limit },
  });
}

export async function getDeviceSpec(id: string) {
  return request<DeviceSpec>(`/api/v1/device-specs/${id}`, {
    method: 'GET',
  });
}

export async function createDeviceSpec(payload: DeviceSpecPayload) {
  return request<DeviceSpec>('/api/v1/device-specs', {
    method: 'POST',
    data: payload,
  });
}

export async function updateDeviceSpec(id: string, payload: Partial<DeviceSpecPayload>) {
  return request<DeviceSpec>(`/api/v1/device-specs/${id}`, {
    method: 'PUT',
    data: payload,
  });
}

export async function deleteDeviceSpec(id: string) {
  return request<{ message: string }>(`/api/v1/device-specs/${id}`, {
    method: 'DELETE',
  });
}
