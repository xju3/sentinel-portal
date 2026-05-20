import { request } from '@umijs/max';

export type Location = {
  id: string;
  name: string;
  description?: string;
  status: number;
  tenant_id: string;
};

export type LocationPayload = {
  name: string;
  description?: string;
  status: number;
};

export type PagedLocationResult = {
  items: Location[];
  total: number;
};

export async function listAllLocations() {
  const pageSize = 100;
  let current = 1;
  const all: Location[] = [];

  while (true) {
    const result = await request<PagedLocationResult>('/api/v1/locations', {
      method: 'GET',
      params: { current, pageSize },
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
) {
  return request<PagedLocationResult>('/api/v1/locations', {
    method: 'GET',
    params: { current, pageSize, keyword },
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
