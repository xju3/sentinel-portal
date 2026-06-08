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
  [key: string]: 'ascend' | 'descend' | undefined;
}

export interface PagedResult<T> {
  data: T[];
  total: number;
  success: boolean;
}

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
  return { sort_by, sort_order };
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
      total: result.total,
      success: true,
    };
  };
}