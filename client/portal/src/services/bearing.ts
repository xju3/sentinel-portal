import { request } from '@umijs/max';
import {
  requestAllListItems,
  requestPagedList,
  type PagedResult,
  type SortParams,
} from '@/utils/proTableRequest';

export const BEARING_TYPE_OPTIONS = [
  { label: '深沟球轴承', value: 'DEEP_GROOVE_BALL' },
  { label: '角接触球轴承', value: 'ANGULAR_CONTACT_BALL' },
  { label: '调心球轴承', value: 'SELF_ALIGNING_BALL' },
  { label: '圆柱滚子轴承', value: 'CYLINDRICAL_ROLLER' },
  { label: '圆锥滚子轴承', value: 'TAPERED_ROLLER' },
  { label: '调心滚子轴承', value: 'SPHERICAL_ROLLER' },
  { label: '滚针轴承', value: 'NEEDLE_ROLLER' },
  { label: '推力球轴承', value: 'THRUST_BALL' },
  { label: '推力滚子轴承', value: 'THRUST_ROLLER' },
  { label: '其他', value: 'OTHER' },
] as const;

export type BearingType = (typeof BEARING_TYPE_OPTIONS)[number]['value'];

export const getBearingTypeLabel = (bearingType?: string | null) =>
  BEARING_TYPE_OPTIONS.find((option) => option.value === bearingType)?.label ||
  bearingType ||
  '-';

export type BearingModel = {
  id: string;
  tenant_id: string;
  brand: string;
  model: string;
  bearing_type?: BearingType | null;
  rolling_element_count: number;
  rolling_element_diameter_mm: number;
  pitch_diameter_mm: number;
  contact_angle_deg: number;
  description?: string | null;
  active: boolean;
};

export type BearingModelPayload = {
  brand: string;
  model: string;
  bearing_type?: BearingType | null;
  rolling_element_count: number;
  rolling_element_diameter_mm: number;
  pitch_diameter_mm: number;
  contact_angle_deg: number;
  description?: string;
  active: boolean;
};

export type BearingQueryParams = {
  current?: number;
  pageSize?: number;
  keyword?: string;
  activeOnly?: boolean;
  brand?: string;
  model?: string;
};

export type BearingPagedResult = PagedResult<BearingModel>;

export async function listAllBearings(activeOnly = false) {
  return requestAllListItems<BearingModel>(
    '/api/v1/bearings',
    { active: activeOnly || undefined },
    100,
  );
}

export async function queryBearings(
  params: BearingQueryParams = {},
  sort: SortParams = {},
): Promise<BearingPagedResult> {
  const { activeOnly, ...rest } = params;
  return requestPagedList<BearingModel>('/api/v1/bearings', {
    params: {
      ...rest,
      active: activeOnly,
    },
    sort,
    defaultPageSize: 20,
  });
}

export async function createBearing(payload: BearingModelPayload) {
  return request<BearingModel>('/api/v1/bearings', {
    method: 'POST',
    data: payload,
  });
}

export async function updateBearing(id: string, payload: Partial<BearingModelPayload>) {
  return request<BearingModel>(`/api/v1/bearings/${id}`, {
    method: 'PUT',
    data: payload,
  });
}

export async function deleteBearing(id: string) {
  return request<{ message: string }>(`/api/v1/bearings/${id}`, {
    method: 'DELETE',
  });
}
