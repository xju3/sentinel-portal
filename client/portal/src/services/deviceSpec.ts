import { request } from '@umijs/max';
import { listAllSuppliers } from '@/services/supplier';
import type { Supplier } from '@/services/supplier';
import type { BearingModel } from '@/services/bearing';
import type { PointTrendValue } from '@/services/deviceHealthArchive';
import {
  requestAllListItems,
  requestPagedList,
  type PagedResult,
  type SortParams,
} from '@/utils/proTableRequest';

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
  process_device_count?: number;
  process_devices?: Array<{ id: string; code: string; sn: string }>;
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
  name?: string;
  model?: string;
  brand?: string;
  supplier_id?: string;
  device_category_id?: string;
  rpm?: number;
  voltage?: number;
  process_device_id?: string;
};

export type DeviceSpecPagedResult = PagedResult<DeviceSpec>;

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
  return requestAllListItems<DeviceSpec>(
    '/api/v1/device-specs',
    { process_device_id: processDeviceId || undefined },
    100,
  );
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
  params: Record<string, any> = {},
  sort: SortParams = {},
) {
  return requestPagedList<DeviceSpec>('/api/v1/device-specs', {
    params,
    sort,
    defaultPageSize: 20,
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
