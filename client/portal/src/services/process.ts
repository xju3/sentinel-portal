import { request } from '@umijs/max';
import {
  requestAllListItems,
  requestPagedList,
  type PagedResult,
  type SortParams,
} from '@/utils/proTableRequest';

export type Process = {
  id: string;
  tenant_id?: string;
  code: string;
  name: string;
  status: number;
  remark?: string;
};

export type ProcessPayload = {
  tenant_id?: string;
  code: string;
  name: string;
  status: number;
  remark?: string;
};

export type ProcessItem = {
  id: string;
  process_id: string;
  device_spec_id: string;
  qty: number;
  device_spec?: { id: string; name: string; model: string; brand: string } | null;
};

export type ProcessItemPayload = {
  process_id: string;
  device_spec_id: string;
  qty: number;
};

export type ProcessDevice = {
  id: string;
  code: string;
  process_id: string;
  sn: string;
  area_id?: string | null;
  status: number;
  employees?: { id: string; name: string }[] | null;
  process?: { id: string; name: string; code: string };
  area?: { id: string; name: string };
};

export type ProcessDevicePayload = {
  code: string;
  process_id: string;
  sn: string;
  area_id?: string | null;
  status: number;
};

export type ProcessDeviceItem = {
  id: string;
  code: string;
  desc: string;
  device_inst_id: string;
  process_device_id: string;
  color: string;
};

export type ProcessDeviceItemPayload = {
  code: string;
  desc: string;
  device_inst_id: string;
  process_device_id: string;
  color: string;
};

export type ProcessPagedResult = PagedResult<Process>;
export type ProcessItemPagedResult = PagedResult<ProcessItem>;
export type ProcessDevicePagedResult = PagedResult<ProcessDevice>;
export type ProcessDeviceItemPagedResult = PagedResult<ProcessDeviceItem>;

export async function listAllProcesses() {
  return requestAllListItems<Process>('/api/v1/processes');
}

export async function createProcess(payload: ProcessPayload) {
  return request<Process>('/api/v1/processes', {
    method: 'POST',
    data: payload,
  });
}

export async function updateProcess(id: string, payload: Partial<ProcessPayload>) {
  return request<Process>(`/api/v1/processes/${id}`, {
    method: 'PUT',
    data: payload,
  });
}

export async function deleteProcess(id: string) {
  return request<{ message: string }>(`/api/v1/processes/${id}`, {
    method: 'DELETE',
  });
}

export async function listAllProcessItems() {
  return requestAllListItems<ProcessItem>('/api/v1/process-items');
}

export async function createProcessItem(payload: ProcessItemPayload) {
  return request<ProcessItem>('/api/v1/process-items', {
    method: 'POST',
    data: payload,
  });
}

export async function updateProcessItem(id: string, payload: Partial<ProcessItemPayload>) {
  return request<ProcessItem>(`/api/v1/process-items/${id}`, {
    method: 'PUT',
    data: payload,
  });
}

export async function deleteProcessItem(id: string) {
  return request<{ message: string }>(`/api/v1/process-items/${id}`, {
    method: 'DELETE',
  });
}

export async function listAllProcessDevices(deviceSpecId?: string) {
  return requestAllListItems<ProcessDevice>(
    '/api/v1/process-devices',
    { device_spec_id: deviceSpecId || undefined },
    100,
  );
}

export async function createProcessDevice(payload: ProcessDevicePayload) {
  return request<ProcessDevice>('/api/v1/process-devices', {
    method: 'POST',
    data: payload,
  });
}

export async function updateProcessDevice(id: string, payload: Partial<ProcessDevicePayload>) {
  return request<ProcessDevice>(`/api/v1/process-devices/${id}`, {
    method: 'PUT',
    data: payload,
  });
}

export async function deleteProcessDevice(id: string) {
  return request<{ message: string }>(`/api/v1/process-devices/${id}`, {
    method: 'DELETE',
  });
}

export async function updateProcessDeviceEmployees(id: string, employee_ids: string[]) {
  return request(`/api/v1/process-devices/${id}/employees`, {
    method: 'POST',
    data: { employee_ids },
  });
}

export async function listAllProcessDeviceItems() {
  return requestAllListItems<ProcessDeviceItem>('/api/v1/process-device-items');
}

export async function createProcessDeviceItem(payload: ProcessDeviceItemPayload) {
  return request<ProcessDeviceItem>('/api/v1/process-device-items', {
    method: 'POST',
    data: payload,
  });
}

export async function updateProcessDeviceItem(id: string, payload: Partial<ProcessDeviceItemPayload>) {
  return request<ProcessDeviceItem>(`/api/v1/process-device-items/${id}`, {
    method: 'PUT',
    data: payload,
  });
}

export async function deleteProcessDeviceItem(id: string) {
  return request<{ message: string }>(`/api/v1/process-device-items/${id}`, {
    method: 'DELETE',
  });
}


export async function queryProcesses(
  params: Record<string, any> = {},
  sort: SortParams = {},
) {
  return requestPagedList<Process>('/api/v1/processes', {
    params,
    sort,
    defaultPageSize: 20,
  });
}

export async function queryProcessItems(
  params: Record<string, any> = {},
  sort: SortParams = {},
) {
  return requestPagedList<ProcessItem>('/api/v1/process-items', {
    params,
    sort,
    defaultPageSize: 20,
  });
}

export async function queryProcessDevices(
  params: Record<string, any> = {},
  sort: SortParams = {},
) {
  return requestPagedList<ProcessDevice>('/api/v1/process-devices', {
    params,
    sort,
    defaultPageSize: 20,
  });
}

export async function queryProcessDeviceItems(
  params: Record<string, any> = {},
  sort: SortParams = {},
) {
  return requestPagedList<ProcessDeviceItem>('/api/v1/process-device-items', {
    params,
    sort,
    defaultPageSize: 20,
  });
}
