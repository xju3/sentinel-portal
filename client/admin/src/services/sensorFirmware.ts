import { request } from '@umijs/max';

export type SensorFirmware = {
  id: string;
  version: string;
  description?: string;
  release_date?: string;
  file_url: string;
  sensor_type_id: string;
  tenant_id?: string;
  status: number;
};

export type SensorFirmwarePayload = {
  version: string;
  description?: string;
  release_date?: string;
  file_url: string;
  sensor_type_id: string;
  tenant_id?: string;
  status?: number;
};

export async function querySensorFirmwareList(
  params?: any,
  options?: { [key: string]: any },
) {
  return request('/api/v1/admin/sensor-firmwares', {
    method: 'GET',
    params: {
      skip: 0,
      limit: 100,
      ...params,
    },
    ...(options || {}),
  });
}

export async function createSensorFirmware(
  body?: any,
  options?: { [key: string]: any },
) {
  return request('/api/v1/admin/sensor-firmwares', {
    method: 'POST',
    data: body,
    ...(options || {}),
  });
}

export async function updateSensorFirmware(
  id: string,
  body?: any,
  options?: { [key: string]: any },
) {
  return request(`/api/v1/admin/sensor-firmwares/${id}`, {
    method: 'PUT',
    data: body,
    ...(options || {}),
  });
}

export async function deleteSensorFirmware(
  id: string,
  options?: { [key: string]: any },
) {
  return request(`/api/v1/admin/sensor-firmwares/${id}`, {
    method: 'DELETE',
    ...(options || {}),
  });
}

export async function releaseSensorFirmware(
  id: string,
  options?: { [key: string]: any },
) {
  return request(`/api/v1/admin/sensor-firmwares/${id}/release`, {
    method: 'POST',
    ...(options || {}),
  });
}

export type PresignedUploadResponse = {
  presigned_url: string;
  file_url: string;
  object_name: string;
};

export async function getPresignedUploadUrl(
  version: string,
  filename: string,
  options?: { [key: string]: any },
) {
  return request<PresignedUploadResponse>('/api/v1/admin/sensor-firmwares/presigned-upload', {
    method: 'POST',
    data: { version, filename },
    ...(options || {}),
  });
}
