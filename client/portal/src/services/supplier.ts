import { request } from '@umijs/max';

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

export type SupplierPagedResult = {
  items: Supplier[];
  total: number;
};

export async function listAllSuppliers(
  sort_by?: string,
  sort_order?: string,
) {
  const limit = 100;
  let skip = 0;
  const all: Supplier[] = [];

  while (true) {
    const batch =
      (await request<Supplier[]>('/api/v1/suppliers', {
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

export async function querySuppliers(params: SupplierQueryParams = {}): Promise<SupplierPagedResult> {
  const current = params.current || 1;
  const pageSize = params.pageSize || 10;
  const skip = (current - 1) * pageSize;
  const list =
    (await request<Supplier[]>('/api/v1/suppliers', {
      method: 'GET',
      params: {
        skip,
        limit: pageSize,
        keyword: params.keyword || undefined,
      },
    })) || [];

  const countRes = await request<{ total: number }>('/api/v1/suppliers/count', {
    method: 'GET',
    params: {
      keyword: params.keyword || undefined,
    },
  });

  return {
    items: list,
    total: countRes?.total || 0,
  };
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
