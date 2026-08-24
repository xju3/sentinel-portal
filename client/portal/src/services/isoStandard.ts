import { request } from '@umijs/max';
import {
  requestAllListItems,
  requestPagedList,
  type PagedResult,
  type SortParams,
} from '@/utils/proTableRequest';

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
  keyword?: string;
  code?: string;
  version?: number;
  category?: number;
  foundation?: number;
};

export type IsoStandardPagedResult = PagedResult<IsoStandard>;

export async function listAllIsoStandards(
  sort_by?: string,
  sort_order?: string,
) {
  return requestAllListItems<IsoStandard>(
    '/api/v1/iso-standards',
    { sort_by, sort_order },
    100,
  );
}

export async function queryIsoStandards(
  params: IsoStandardQueryParams = {},
  sort: SortParams = {},
): Promise<IsoStandardPagedResult> {
  return requestPagedList<IsoStandard>('/api/v1/iso-standards', {
    params,
    sort,
    defaultPageSize: 20,
  });
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
