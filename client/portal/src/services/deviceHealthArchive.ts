import { request } from '@umijs/max';

export type HealthArchiveBucketStatus =
  | 'normal'
  | 'attention'
  | 'abnormal'
  | 'warning'
  | 'critical'
  | 'missed'
  | 'waiting'
  | 'processing'
  | 'no_data';

export type HealthArchiveBucket = {
  startAt: string;
  endAt: string;
  status: HealthArchiveBucketStatus;
  level: number | null;
  diagnosedCount: number;
  normalCount: number;
  abnormalCount: number;
  missedCount: number;
  waitingCount: number;
  receivedCount: number;
  hasGap: boolean;
};

export type DeviceHealthArchive = {
  device: {
    id: string;
    name: string;
    code: string;
  };
  range: {
    startAt: string;
    endAt: string;
    intervalHours: number;
    bucketCount: number;
  };
  summary: {
    diagnosedCount: number;
    normalCount: number;
    abnormalCount: number;
    missedCount: number;
    waitingCount: number;
    receivedCount: number;
  };
  buckets: HealthArchiveBucket[];
};

export async function getDeviceHealthArchive(
  deviceId: string,
  params: {
    startAt: string;
    endAt: string;
    intervalHours: number;
  },
) {
  return request<DeviceHealthArchive>(`/api/v1/devices/${deviceId}/health-archive`, {
    method: 'GET',
    params: {
      start_at: params.startAt,
      end_at: params.endAt,
      interval_hours: params.intervalHours,
    },
  });
}
