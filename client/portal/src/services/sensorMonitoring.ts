import { request } from '@umijs/max';

export type SensorMonitoring = {
  id: string;
  device_inst_id: string;
  location_id?: string | null;
  sensor_id?: string | null;
  direction?: string | null;
  anomaly: number;
  ts?: number | null;
  status: number;
  bound_at: string;
  unbound_at?: string | null;
  device_inst?: { code: string; name: string } | null;
  location?: { name: string } | null;
  sensor?: { sn: string } | null;
};

export type SensorMonitoringPayload = {
  device_inst_id: string;
  location_id?: string | null;
  sensor_id?: string | null;
  direction?: string | null;
  status: number;
};

export type SensorMonitoringDeviceInstOption = {
  id: string;
  code: string;
  name: string;
  device_spec_id: string;
};

export async function listAllSensorMonitorings() {
  const limit = 100;
  let skip = 0;
  const all: SensorMonitoring[] = [];

  while (true) {
    const res = await request<any>('/api/v1/sensor-monitorings', {
        method: 'GET',
        params: { skip, limit },
      });
    const batch = res?.data?.items || res?.items || res || [];
    all.push(...batch);
    if (batch.length < limit) {
      break;
    }
    skip += limit;
  }

  return all;
}

export type PagedDeviceInstResult = {
  items: SensorMonitoringDeviceInstOption[];
  total: number;
};

export async function listSensorMonitoringDeviceInstOptions() {
  return request<SensorMonitoringDeviceInstOption[]>('/api/v1/sensor-monitorings/device-insts', {
    method: 'GET',
  });
}

export async function querySensorMonitoringDeviceInsts(
  current: number,
  pageSize: number,
  keyword?: string,
) {
  return request<PagedDeviceInstResult>('/api/v1/sensor-monitorings/device-insts', {
    method: 'GET',
    params: { current, pageSize, keyword },
  });
}

export async function createSensorMonitoring(payload: SensorMonitoringPayload) {
  return request<SensorMonitoring>('/api/v1/sensor-monitorings', {
    method: 'POST',
    data: payload,
  });
}

export async function updateSensorMonitoring(
  id: string,
  payload: Partial<SensorMonitoringPayload>,
) {
  return request<SensorMonitoring>(`/api/v1/sensor-monitorings/${id}`, {
    method: 'PUT',
    data: payload,
  });
}

export async function disableSensorMonitoring(id: string) {
  return updateSensorMonitoring(id, { status: 0 });
}
