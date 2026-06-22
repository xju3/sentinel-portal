import { request } from '@umijs/max';

export type Region = {
  id: string;
  name: string;
  province: string;
  prefecture: string;
  county: string;
  level: number;
  available: boolean;
};

export async function listProvinces() {
  return request<Region[]>('/api/v1/regions/provinces', {
    method: 'GET',
  });
}
