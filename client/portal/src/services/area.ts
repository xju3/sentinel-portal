import { request } from '@umijs/max';
import { requestAllListItems, requestPagedList, type SortParams } from '@/utils/proTableRequest';

export type Area = {
  id: string;
  name: string;
  description?: string;
  network: number;
  ssid?: string;
  passwd?: string;
  parent_id?: string | null;
  parent?: { id: string; name: string } | null;
  tenant_id: string;
};

export type AreaPayload = {
  name: string;
  description?: string;
  network?: number;
  ssid?: string;
  passwd?: string;
  parent_id?: string | null;
};

export async function listAllAreas() {
  return requestAllListItems<Area>('/api/v1/areas');
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


export async function queryAreas(params: Record<string, any> = {}, sort: SortParams = {}) {
  return requestPagedList<Area>('/api/v1/areas', {
    params,
    sort,
    defaultPageSize: 20,
  });
}
