import { request } from '@umijs/max';

export type Process = {
  id: string;
  tenant_id?: string;
  code: string;
  name: string;
  status: number;
};

export type ProcessPayload = {
  tenant_id?: string;
  code: string;
  name: string;
  status: number;
};

export type ProcessItem = {
  id: string;
  process_id: string;
  device_spec_id: string;
  qty: number;
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
  status: number;
};

export type ProcessDevicePayload = {
  code: string;
  process_id: string;
  sn: string;
  status: number;
};

export type ProcessDeviceItem = {
  id: string;
  code: string;
  desc: string;
  device_inst_id: string;
  process_device_id: string;
};

export type ProcessDeviceItemPayload = {
  code: string;
  desc: string;
  device_inst_id: string;
  process_device_id: string;
};

export async function listAllProcesses() {
  const limit = 100;
  let skip = 0;
  const all: Process[] = [];

  while (true) {
    const batch =
      (await request<Process[]>('/api/v1/processes', {
        method: 'GET',
        params: { skip, limit },
      })) || [];
    all.push(...batch);
    if (batch.length < limit) {
      break;
    }
    skip += limit;
  }

  return all;
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
  const limit = 100;
  let skip = 0;
  const all: ProcessItem[] = [];

  while (true) {
    const batch =
      (await request<ProcessItem[]>('/api/v1/process-items', {
        method: 'GET',
        params: { skip, limit },
      })) || [];
    all.push(...batch);
    if (batch.length < limit) {
      break;
    }
    skip += limit;
  }

  return all;
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

export async function listAllProcessDevices() {
  const limit = 100;
  let skip = 0;
  const all: ProcessDevice[] = [];

  while (true) {
    const batch =
      (await request<ProcessDevice[]>('/api/v1/process-devices', {
        method: 'GET',
        params: { skip, limit },
      })) || [];
    all.push(...batch);
    if (batch.length < limit) {
      break;
    }
    skip += limit;
  }

  return all;
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

export async function listAllProcessDeviceItems() {
  const limit = 100;
  let skip = 0;
  const all: ProcessDeviceItem[] = [];

  while (true) {
    const batch =
      (await request<ProcessDeviceItem[]>('/api/v1/process-device-items', {
        method: 'GET',
        params: { skip, limit },
      })) || [];
    all.push(...batch);
    if (batch.length < limit) {
      break;
    }
    skip += limit;
  }

  return all;
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
