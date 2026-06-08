import { request } from '@umijs/max';

// ==========================================
// Sensor Firmware Management
// ==========================================

export async function listSensorFirmwares(params: { skip?: number; limit?: number }) {
  return request('/api/admin/sensor-firmwares', {
    method: 'GET',
    params,
  });
}

export async function createSensorFirmware(data: Record<string, any>) {
  return request('/api/admin/sensor-firmwares', {
    method: 'POST',
    data,
  });
}

export async function updateSensorFirmware(id: string, data: Record<string, any>) {
  return request(`/api/admin/sensor-firmwares/${id}`, {
    method: 'PUT',
    data,
  });
}

export async function deleteSensorFirmware(id: string) {
  return request(`/api/admin/sensor-firmwares/${id}`, {
    method: 'DELETE',
  });
}

export async function releaseSensorFirmware(id: string) {
  return request(`/api/admin/sensor-firmwares/${id}/release`, {
    method: 'POST',
  });
}

// ==========================================
// Helper fetchers for dropdowns
// ==========================================
export async function getSensorTypesOptions() {
  return request('/api/sensors/types', { method: 'GET', params: { skip: 0, limit: 1000 } });
}

export async function getTenantsOptions() {
  return request('/api/tenants', { method: 'GET', params: { skip: 0, limit: 1000 } });
}