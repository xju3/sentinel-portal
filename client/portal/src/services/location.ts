import { request } from '@umijs/max';
import {
  requestAllListItems,
  requestPagedList,
  type PagedResult,
  type SortParams,
} from '@/utils/proTableRequest';

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

export type PagedLocationResult = PagedResult<Location>;

export async function listAllLocations(
  options: { sort_field?: string; sort_order?: string; bearingOnly?: boolean } = {},
) {
  return requestAllListItems<Location>(
    '/api/v1/locations',
    {
      sort_by: options.sort_field,
      sort_order: options.sort_order,
      bearing_only: options.bearingOnly,
      active_only: false,
    },
    100,
  );
}

export function queryLocations(
  params?: Record<string, any>,
  sort?: SortParams,
): Promise<PagedResult<Location>>;
export function queryLocations(
  current?: number,
  pageSize?: number,
  keyword?: string,
  bearingOnly?: boolean,
): Promise<PagedResult<Location>>;
export async function queryLocations(
  currentOrParams: number | Record<string, any> = {},
  pageSizeOrSort?: number | SortParams,
  keyword?: string,
  bearingOnly = false,
) {
  const params =
    typeof currentOrParams === 'number'
      ? {
          current: currentOrParams,
          pageSize: typeof pageSizeOrSort === 'number' ? pageSizeOrSort : 20,
          keyword,
          bearing_only: bearingOnly,
          active_only: true,
        }
      : {
          ...currentOrParams,
        };
  const sort =
    typeof currentOrParams === 'number'
      ? {}
      : ((pageSizeOrSort as SortParams | undefined) || {});

  return requestPagedList<Location>('/api/v1/locations', {
    params,
    sort,
    defaultPageSize: 20,
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

export async function disableLocation(id: string) {
  return updateLocation(id, { status: 0 });
}
