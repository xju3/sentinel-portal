import { request } from '@umijs/max';

export type Location = {
  id: string;
  name: string;
  description?: string;
  is_bearing_point: boolean;
  status: number;
  tenant_id: string;
};

export type LocationPayload = {
  name: string;
  description?: string;
  is_bearing_point: boolean;
  status: number;
};

export type PagedLocationResult = {
  items: Location[];
  total: number;
};

export async function listAllLocations(
  options: { sort_field?: string; sort_order?: string; bearingOnly?: boolean } = {},
) {
  const pageSize = 100;
  let current = 1;
  const all: Location[] = [];

  while (true) {
    const result = await request<PagedLocationResult>('/api/v1/locations', {
      method: 'GET',
      params: {
        current,
        pageSize,
        sort_by: options.sort_field,
        sort_order: options.sort_order,
        bearing_only: options.bearingOnly,
      },
    });
    all.push(...result.items);
    if (result.items.length < pageSize) {
      break;
    }
    current++;
  }

  return all;
}

export async function queryLocations(
  current: number,
  pageSize: number,
  keyword?: string,
  bearingOnly = false,
) {
  return request<PagedLocationResult>('/api/v1/locations', {
    method: 'GET',
    params: { current, pageSize, keyword, bearing_only: bearingOnly },
  });
}

export async function createLocation(payload: LocationPayload) {
  return request<Location>('/api/v1/locations', {
    method: 'POST',
    data: payload,
  });
}

export async function updateLocation(id: string, payload: Partial<LocationPayload>) {
  return request<Location>(`/api/v1/locations/${id}`, {
    method: 'PUT',
    data: payload,
  });
}

export async function deleteLocation(id: string) {
  return request<{ message: string }>(`/api/v1/locations/${id}`, {
    method: 'DELETE',
  });
}
