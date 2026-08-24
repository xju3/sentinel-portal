import { request } from '@umijs/max';
import {
  requestAllListItems,
  requestPagedList,
  type PagedResult,
  type SortParams,
} from '@/utils/proTableRequest';

export type Supplier = {
  id: string;
  name: string;
  brand: string;
  contact_info?: string;
  active: boolean;
};

export type SupplierPayload = {
  name: string;
  brand: string;
  contact_info?: string;
  active: boolean;
};

export type SupplierQueryParams = {
  current?: number;
  pageSize?: number;
  keyword?: string;
};

export type SupplierPagedResult = PagedResult<Supplier>;

export async function listAllSuppliers(
  sort_by?: string,
  sort_order?: string,
) {
  return requestAllListItems<Supplier>(
    '/api/v1/suppliers',
    { sort_by, sort_order },
    100,
  );
}

export async function querySuppliers(
  params: SupplierQueryParams = {},
  sort: SortParams = {},
): Promise<SupplierPagedResult> {
  return requestPagedList<Supplier>('/api/v1/suppliers', {
    params,
    sort,
    defaultPageSize: 20,
  });
}

export async function createSupplier(payload: SupplierPayload) {
  return request<Supplier>('/api/v1/suppliers', {
    method: 'POST',
    data: payload,
  });
}

export async function updateSupplier(id: string, payload: Partial<SupplierPayload>) {
  return request<Supplier>(`/api/v1/suppliers/${id}`, {
    method: 'PUT',
    data: payload,
  });
}

export async function deleteSupplier(id: string) {
  return request<{ message: string }>(`/api/v1/suppliers/${id}`, {
    method: 'DELETE',
  });
}
