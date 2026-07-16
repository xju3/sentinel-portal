import { request } from '@umijs/max';

export interface SimCardItem {
  id: string;
  iccid: string;
  carrier: string;
  data_plan: string;
  activated_at?: string;
  expires_at: string;
  status: number;
  bound: number;
}

/** 获取 SIM 卡列表 */
export async function getSimCards(params: {
  current?: number;
  pageSize?: number;
  keyword?: string;
  status?: number;
  unbound_only?: boolean;
  unactivated_only?: boolean;
  sort_by?: string;
  sort_order?: string;
}) {
  return request('/api/v1/sim-cards/', {
    method: 'GET',
    params: {
      ...params,
      page_size: params.pageSize, // 将前端的 pageSize 映射到后端的 page_size
    },
  });
}

/** 创建 SIM 卡 */
export async function addSimCard(data: Partial<SimCardItem>) {
  return request('/api/v1/sim-cards/', {
    method: 'POST',
    data,
  });
}

/** 批量创建 SIM 卡 */
export async function addSimCardBatch(data: any) {
  return request('/api/v1/sim-cards/batch', {
    method: 'POST',
    data,
  });
}

/** 更新 SIM 卡 */
export async function updateSimCard(id: string, data: Partial<SimCardItem>) {
  return request(`/api/v1/sim-cards/${id}`, {
    method: 'PUT',
    data,
  });
}

/** 删除 SIM 卡 */
export async function removeSimCard(id: string) {
  return request(`/api/v1/sim-cards/${id}`, {
    method: 'DELETE',
  });
}