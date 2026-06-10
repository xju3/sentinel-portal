import { request } from '@umijs/max';

export type SensorType = {
  id: string;
  name: string;
  battery: number;
  network: number;
  bluetooth: boolean;
  description?: string;
};

export async function listSensorTypes() {
  const limit = 100;
  let skip = 0;
  const all: SensorType[] = [];

  while (true) {
    const batch =
      (await request<SensorType[]>('/api/v1/sensors/types', {
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
