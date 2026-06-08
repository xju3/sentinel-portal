import { request } from '@umijs/max';

export async function getSensorHistory(sn: string, range: string, window?: string) {
  return request(`/api/v1/sensors/${sn}/history`, {
    method: 'GET',
    params: { range, window },
  });
}