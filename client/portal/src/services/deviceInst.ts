import { request } from '@umijs/max';

export type DeviceInst = {
  id: string;
  name: string;
  device_spec_id: string;
  code: string;
  purchase_date: string;
  life_span: number;
  desc: string;
  status: number;
  active: number;
  available: number;
  device_spec?: { id: string; name: string; model: string; brand: string };
};

export type DeviceInstPayload = {
  name: string;
  device_spec_id: string;
  code: string;
  purchase_date: string;
  life_span: number;
  desc: string;
  status: number;
  active: number;
  available: number;
};

export async function listAllDeviceInsts() {
  const limit = 100;
  let skip = 0;
  const all: DeviceInst[] = [];

  while (true) {
    const batch =
      (await request<DeviceInst[]>('/api/v1/device-insts', {
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

export async function createDeviceInst(payload: DeviceInstPayload) {
  return request<DeviceInst>('/api/v1/device-insts', {
    method: 'POST',
    data: payload,
  });
}

export async function updateDeviceInst(id: string, payload: Partial<DeviceInstPayload>) {
  return request<DeviceInst>(`/api/v1/device-insts/${id}`, {
    method: 'PUT',
    data: payload,
  });
}

export async function deleteDeviceInst(id: string) {
  return request<{ message: string }>(`/api/v1/device-insts/${id}`, {
    method: 'DELETE',
  });
}
