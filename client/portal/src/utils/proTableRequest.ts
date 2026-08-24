import { request } from '@umijs/max';

/**
 * Shared ProTable request helpers for server-side pagination + sorting.
 *
 * ProTable passes `sort` as an object where keys are column dataIndex values
 * and values are "ascend" | "descend" | undefined.
 *
 * We take the first active sort key and pass it to the API as:
 *   sort_by=key  sort_order=ascend|descend
 */

export interface PageParams {
  current?: number;
  pageSize?: number;
  [key: string]: any;
}

export interface SortParams {
  [key: string]: 'ascend' | 'descend' | null | undefined;
}

export interface PagedResult<T> {
  data: T[];
  items?: T[];
  total: number;
  success: boolean;
}

type RawPagedPayload<T> =
  | {
      items?: T[];
      total?: number;
      data?: {
        items?: T[];
        total?: number;
      };
    }
  | T[];

type RequestListOptions = {
  method?: 'GET' | 'POST';
  params?: Record<string, any>;
  sort?: SortParams;
  defaultPageSize?: number;
};

/**
 * Extract sort_by and sort_order from ProTable's sort object.
 */
export function extractSortFromProTable(sort: SortParams = {}): {
  sort_by?: string;
  sort_order?: string;
} {
  const entries = Object.entries(sort || {}).filter(
    ([_, order]) => order === 'ascend' || order === 'descend',
  );
  if (entries.length === 0) {
    return {};
  }
  const [sort_by, sort_order] = entries[0];
  return { sort_by, sort_order: sort_order || undefined };
}

export function normalizePagedPayload<T>(payload: RawPagedPayload<T>): {
  items: T[];
  total: number;
} {
  if (Array.isArray(payload)) {
    return {
      items: payload,
      total: payload.length,
    };
  }

  const unwrapped = payload?.data && !Array.isArray(payload.data) ? payload.data : payload;
  const items = Array.isArray(unwrapped?.items) ? unwrapped.items : [];
  const total = typeof unwrapped?.total === 'number' ? unwrapped.total : items.length;

  return { items, total };
}

export function buildPagedParams(
  params: PageParams = {},
  sort: SortParams = {},
  defaultPageSize = 20,
) {
  const {
    current,
    pageSize,
    skip,
    limit,
    sort_by,
    sort_order,
    field,
    order,
    ...rest
  } = params;

  const resolvedPageSize = Number(pageSize || limit || defaultPageSize) || defaultPageSize;
  const resolvedSkip =
    typeof skip === 'number' || typeof skip === 'string'
      ? Math.max(Number(skip) || 0, 0)
      : Math.max((Number(current || 1) - 1) * resolvedPageSize, 0);
  const resolvedSort = sort_by || sort_order
    ? { sort_by, sort_order }
    : field && order
      ? { sort_by: field, sort_order: order }
      : extractSortFromProTable(sort);

  const queryParams = Object.fromEntries(
    Object.entries({
      ...rest,
      skip: resolvedSkip,
      limit: resolvedPageSize,
      ...resolvedSort,
    }).filter(([, value]) => value !== undefined && value !== null && value !== ''),
  );

  return {
    current: Number(current || 1) || 1,
    pageSize: resolvedPageSize,
    skip: resolvedSkip,
    limit: resolvedPageSize,
    queryParams,
  };
}

export async function requestPagedList<T>(
  url: string,
  options: RequestListOptions = {},
): Promise<PagedResult<T>> {
  const {
    method = 'GET',
    params = {},
    sort = {},
    defaultPageSize = 20,
  } = options;
  const { queryParams } = buildPagedParams(params, sort, defaultPageSize);
  const payload = await request<RawPagedPayload<T>>(url, {
    method,
    params: queryParams,
  });
  const { items, total } = normalizePagedPayload<T>(payload);

  return {
    data: items,
    items,
    total,
    success: true,
  };
}

export async function requestAllListItems<T>(
  url: string,
  params: Record<string, any> = {},
  defaultPageSize = 100,
): Promise<T[]> {
  const all: T[] = [];
  let current = 1;

  while (true) {
    const page = await requestPagedList<T>(url, {
      params: { ...params, current, pageSize: defaultPageSize },
      defaultPageSize,
    });
    all.push(...page.data);
    if (page.data.length < defaultPageSize || all.length >= page.total) {
      break;
    }
    current += 1;
  }

  return all;
}

/**
 * Build a standard request function for ProTable.
 *
 * Example usage:
 *
 *   const request = buildProTableRequest(async (params, sort) => {
 *     const { current, pageSize } = params;
 *     const skip = (current - 1) * pageSize;
 *     const result = await listXxx({ skip, limit: pageSize, ...extractSortFromProTable(sort) });
 *     return { data: result, total: totalCount };
 *   });
 */
export function buildProTableRequest<T>(
  fetcher: (params: PageParams, sort: SortParams) => Promise<{ data: T[]; total: number }>,
) {
  return async (
    params: PageParams,
    sort: SortParams,
  ): Promise<PagedResult<T>> => {
    const result = await fetcher(params, sort);
    return {
      data: result.data,
      items: result.data,
      total: result.total,
      success: true,
    };
  };
}
