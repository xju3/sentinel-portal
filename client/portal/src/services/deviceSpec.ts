import { request } from '@umijs/max';
import { listAllSuppliers } from '@/services/supplier';
import type { Supplier } from '@/services/supplier';
import type { BearingModel } from '@/services/bearing';

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
  supplier?: { id: string; name: string };
  device_category?: { id: string; name: string };
};

export type DeviceSpecPayload = {
  name: string;
  model: string;
  description?: string;
  brand: string;
  voltage: number;
  rpm: number;
  supplier_id: string;
  device_category_id: string;
};

export type DeviceSpecBearingBinding = {
  id?: string;
  device_spec_id: string;
  bearing_id: string;
  location_id: string;
  shaft_speed_ratio: number;
  enabled: boolean;
  bearing?: BearingModel;
  location?: { id: string; name: string };
};

export type DeviceSpecBearingBindingPayload = {
  bearing_id: string;
  location_id: string;
  shaft_speed_ratio: number;
  enabled: boolean;
};

export type DeviceSpecQueryParams = {
  current?: number;
  pageSize?: number;
  keyword?: string;
};

export type DeviceSpecPagedResult = {
  items: DeviceSpec[];
  total: number;
};

export async function listAllDeviceSpecs() {
  const limit = 100;
  let skip = 0;
  const all: DeviceSpec[] = [];

  while (true) {
    const batch =
      (await request<DeviceSpec[]>('/api/v1/device-specs', {
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

export async function queryDeviceSpecs(
  params: DeviceSpecQueryParams = {},
): Promise<DeviceSpecPagedResult> {
  const current = params.current || 1;
  const pageSize = params.pageSize || 10;
  const keyword = String(params.keyword || '').trim().toLowerCase();

  const all = await listAllDeviceSpecs();
  const filtered = keyword
    ? all.filter((item) =>
      [item.name, item.model, item.brand, item.id].some((part) =>
        String(part || '')
          .toLowerCase()
          .includes(keyword),
      ),
    )
    : all;

  const start = (current - 1) * pageSize;
  return {
    items: filtered.slice(start, start + pageSize),
    total: filtered.length,
  };
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

export async function getDeviceSpecBearingBindings(id: string) {
  return (
    (await request<DeviceSpecBearingBinding[]>(`/api/v1/device-specs/${id}/bearings`, {
      method: 'GET',
    })) || []
  );
}

export async function updateDeviceSpecBearingBindings(
  id: string,
  bindings: DeviceSpecBearingBindingPayload[],
) {
  return request<DeviceSpecBearingBinding[]>(`/api/v1/device-specs/${id}/bearings`, {
    method: 'PUT',
    data: { bindings },
  });
}

export type { Supplier };
export { listAllSuppliers };
