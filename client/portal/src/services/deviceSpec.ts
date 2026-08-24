import { request } from '@umijs/max';
import { listAllSuppliers } from '@/services/supplier';
import type { Supplier } from '@/services/supplier';
import type { BearingModel } from '@/services/bearing';
import type { PointTrendValue } from '@/services/deviceHealthArchive';

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
  remark?: string;
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
  remark?: string;
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

export type DeviceSpecComparisonPoint = PointTrendValue | null;

export type DeviceSpecComparison = {
  meta: {
    rangeDays: number;
    windowMinutes?: number | null;
    raw: boolean;
    patrolMinutes?: number;
    startAt?: string;
    endAt?: string;
    deviceCount: number;
    pointCount: number;
  };
  locations: Array<{
    id: string;
    name: string;
    deviceCount: number;
    activeDeviceCount: number;
  }>;
  selectedLocationId?: string | null;
  selectedLocation?: {
    id: string;
    name: string;
    deviceCount: number;
    activeDeviceCount: number;
  } | null;
  series: Array<{
    device: {
      id: string;
      name: string;
      code: string;
      color: string;
    };
    timestamps: string[];
    temperature: DeviceSpecComparisonPoint[];
    vibration: DeviceSpecComparisonPoint[];
    displacement: DeviceSpecComparisonPoint[];
  }>;
};

export async function listAllDeviceSpecs(processDeviceId?: string) {
  const limit = 100;
  let skip = 0;
  const all: DeviceSpec[] = [];

  while (true) {
    const batch =
      (await request<DeviceSpec[]>('/api/v1/device-specs', {
        method: 'GET',
        params: {
          skip,
          limit,
          process_device_id: processDeviceId || undefined,
        },
      })) || [];
    all.push(...batch);
    if (batch.length < limit) {
      break;
    }
    skip += limit;
  }

  return all;
}

export async function getDeviceSpecComparison(
  deviceSpecId: string,
  params: {
    processDeviceId: string;
    locationId?: string;
    rangeDays: number;
    windowMinutes: number;
  },
) {
  return request<DeviceSpecComparison>(
    `/api/v1/device-specs/${deviceSpecId}/comparison`,
    {
      method: 'GET',
      params: {
        process_device_id: params.processDeviceId,
        location_id: params.locationId,
        range_days: params.rangeDays,
        window_minutes: params.windowMinutes,
      },
    },
  );
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
