import { request } from '@umijs/max';

export type Area = {
  id: string;
  name: string;
  description?: string;
  ssid?: string;
  passwd?: string;
  parent_id?: string | null;
  tenant_id: string;
};

export type AreaPayload = {
  name: string;
  description?: string;
  ssid?: string;
  passwd?: string;
  parent_id?: string | null;
};

export async function listAllAreas() {
  const limit = 100;
  let skip = 0;
  const all: Area[] = [];

  while (true) {
    const batch =
      (await request<Area[]>('/api/v1/areas', {
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

export async function createArea(payload: AreaPayload) {
  return request<Area>('/api/v1/areas', {
    method: 'POST',
    data: payload,
  });
}

export async function updateArea(id: string, payload: Partial<AreaPayload>) {
  return request<Area>(`/api/v1/areas/${id}`, {
    method: 'PUT',
    data: payload,
  });
}

export async function deleteArea(id: string) {
  return request<{ message: string }>(`/api/v1/areas/${id}`, {
    method: 'DELETE',
  });
}
