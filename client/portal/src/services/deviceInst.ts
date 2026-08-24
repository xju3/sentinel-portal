import { request } from '@umijs/max';
import { requestAllListItems, requestPagedList, type SortParams } from '@/utils/proTableRequest';

export type DeviceInst = {
  id: string;
  name: string;
  device_spec_id: string;
  code: string;
  purchase_date?: string | null;
  life_span: number;
  desc?: string | null;
  status: number;
  active: number;
  available: number;
  device_spec?: { id: string; name: string; model: string; brand: string };
  sensor_monitorings?: Array<{
    id: string;
    location?: { id: string; name: string } | null;
    sensor?: { id: string; sn: string } | null;
  }>;
};

export type DeviceInstPayload = {
  name: string;
  device_spec_id: string;
  code: string;
  purchase_date?: string | null;
  life_span: number;
  desc?: string | null;
  status: number;
  active: number;
  available: number;
};

export async function listAllDeviceInsts() {
  return requestAllListItems<DeviceInst>('/api/v1/device-insts');
}

export async function queryDeviceInsts(
  params: Record<string, any> = {},
  sort: SortParams = {},
) {
  return requestPagedList<DeviceInst>('/api/v1/device-insts', {
    params,
    sort,
    defaultPageSize: 20,
  });
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
