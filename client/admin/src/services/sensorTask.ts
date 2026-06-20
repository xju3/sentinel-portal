import { request } from '@umijs/max';

export type SensorTask = {
  id: string;
  name: string;
  sn: string;
  action: number;
  val: number;
  remark?: string | null;
  status: 0 | 1 | 2;
  create_time: string;
  dispatched_at?: string | null;
  complete_time?: string | null;
};

export type SensorTaskPayload = {
  sensor_id: string;
  name: string;
  action: number;
  val: number;
  remark?: string;
};

export type PagedSensorTaskResponse = {
  items: SensorTask[];
  total: number;
};

export async function listSensorTasks(params: {
  current?: number;
  pageSize?: number;
  keyword?: string;
  status?: number;
}) {
  return request<PagedSensorTaskResponse>('/api/v1/sensors/tasks', {
    method: 'GET',
    params,
  });
}

export async function createSensorTask(payload: SensorTaskPayload) {
  return request<SensorTask>('/api/v1/sensors/tasks', {
    method: 'POST',
    data: payload,
  });
}
