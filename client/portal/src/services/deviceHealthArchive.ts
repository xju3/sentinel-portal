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
    rpm?: number;
  };
  points: Array<{
    id: string;
    name: string;
    active: boolean;
    sensor: {
      id: string;
      sn: string;
      description?: string | null;
    } | null;
  }>;
  selectedLocationId: string | null;
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
    locationId?: string;
  },
) {
  return request<DeviceHealthArchive>(`/api/v1/devices/${deviceId}/health-archive`, {
    method: 'GET',
    params: {
      start_at: params.startAt,
      end_at: params.endAt,
      interval_hours: params.intervalHours,
      location_id: params.locationId,
    },
  });
}

export type PointTrendValue = {
  value: number | null;
  min: number | null;
  max: number | null;
  last: number | null;
  count: number;
};

export type DevicePointTrend = {
  meta: {
    rangeDays: number;
    windowMinutes: number;
    raw: boolean;
    patrolMinutes: number;
    startAt: string;
    endAt: string;
    pointCount: number;
  };
  timestamps: string[];
  temperature: Array<PointTrendValue | null>;
  vibration: Array<PointTrendValue | null>;
};

export async function getDevicePointTrend(
  deviceId: string,
  params: {
    locationId: string;
    rangeDays: number;
    windowMinutes: number;
  },
) {
  return request<DevicePointTrend>(`/api/v1/devices/${deviceId}/point-trends`, {
    method: 'GET',
    params: {
      location_id: params.locationId,
      range_days: params.rangeDays,
      window_minutes: params.windowMinutes,
    },
  });
}

export type DeviceFftRecord = {
  id: string;
  ts_ms: number;
  points: number;
  range_g: number;
  fs_hz: number;
};

export type DeviceFftData = {
  ts_ms: number;
  fs_hz: number;
  range_g: number;
  fft_size: number;
  spectrum_bins: number;
  points_preview: number;
  freq_hz: number[];
  x_axis: number[];
  y_axis: number[];
  z_axis: number[];
};

export async function listDeviceFftRecords(deviceId: string) {
  return request<DeviceFftRecord[]>(`/api/v1/devices/${deviceId}/fft-records`, {
    method: 'GET',
  });
}

export async function getDeviceFftData(deviceId: string, recordId: string) {
  return request<DeviceFftData>(`/api/v1/devices/${deviceId}/fft-records/${recordId}/data`, {
    method: 'GET',
  });
}
