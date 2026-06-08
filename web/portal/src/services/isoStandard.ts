import { request } from '@umijs/max';

export type IsoStandard = {
  id: string;
  code: string;
  version: number; // 1: ISO-10816, 2: ISO-20816
  category: number; // version-dependent
  foundation: number; // 1: 刚性基础, 2: 柔性基础
  description?: string;
};

export type IsoStandardPayload = {
  code: string;
  version: number;
  category: number;
  foundation: number;
  description?: string;
};

export type IsoStandardQueryParams = {
  current?: number;
  pageSize?: number;
};

export type IsoStandardPagedResult = {
  items: IsoStandard[];
  total: number;
};

export async function listAllIsoStandards(
  sort_by?: string,
  sort_order?: string,
) {
  const limit = 100;
  let skip = 0;
  const all: IsoStandard[] = [];

  while (true) {
    const batch =
      (await request<IsoStandard[]>('/api/v1/iso-standards', {
        method: 'GET',
        params: { skip, limit, sort_by, sort_order },
      })) || [];
    all.push(...batch);
    if (batch.length < limit) {
      break;
    }
    skip += limit;
  }

  return all;
}

export async function queryIsoStandards(params: IsoStandardQueryParams = {}): Promise<IsoStandardPagedResult> {
  const current = params.current || 1;
  const pageSize = params.pageSize || 10;
  const skip = (current - 1) * pageSize;
  const list =
    (await request<IsoStandard[]>('/api/v1/iso-standards', {
      method: 'GET',
      params: {
        skip,
        limit: pageSize,
      },
    })) || [];

  const countRes = await request<{ total: number }>('/api/v1/iso-standards/count', {
    method: 'GET',
  });

  return {
    items: list,
    total: countRes?.total || 0,
  };
}

export async function createIsoStandard(payload: IsoStandardPayload) {
  return request<IsoStandard>('/api/v1/iso-standards', {
    method: 'POST',
    data: payload,
  });
}

export async function updateIsoStandard(id: string, payload: Partial<IsoStandardPayload>) {
  return request<IsoStandard>(`/api/v1/iso-standards/${id}`, {
    method: 'PUT',
    data: payload,
  });
}

export async function deleteIsoStandard(id: string) {
  return request<{ message: string }>(`/api/v1/iso-standards/${id}`, {
    method: 'DELETE',
  });
}