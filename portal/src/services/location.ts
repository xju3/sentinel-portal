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

export async function listAllLocations() {
  const limit = 100;
  let skip = 0;
  const all: Location[] = [];

  while (true) {
    const batch =
      (await request<Location[]>('/api/v1/locations', {
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
