import { request } from '@umijs/max';
import {
  requestAllListItems,
  requestPagedList,
  type PagedResult,
  type SortParams,
} from '@/utils/proTableRequest';

export type DeviceOperationScheduleItem = {
  id?: string;
  schedule_id?: string;
  cron_expr: string;
  duration_minutes: number;
  remark?: string;
  seq: number;
};

export type DeviceOperationScheduleItemPayload = {
  cron_expr: string;
  duration_minutes: number;
  remark?: string;
  seq: number;
};

export type DeviceOperationSchedule = {
  id: string;
  tenant_id: string;
  code: string;
  name: string;
  description?: string;
  status: number;
  items?: DeviceOperationScheduleItem[];
};

export type DeviceOperationSchedulePayload = {
  code: string;
  name: string;
  description?: string;
  status: number;
};

export type ScheduleCycleType = 'DAILY' | 'WEEKLY' | 'MONTHLY';

export type VisualScheduleSlot = {
  cycleType: ScheduleCycleType;
  weekdays: number[];
  monthDays: number[];
  startTime: string; // "HH:mm"
  endTime: string;   // "HH:mm"
  durationMinutes: number;
  isNextDay: boolean;
  cycleLabel: string;
  timeRangeLabel: string;
  durationLabel: string;
  summaryLabel: string;
};

const WEEKDAY_NAMES: Record<number, string> = {
  1: '周一',
  2: '周二',
  3: '周三',
  4: '周四',
  5: '周五',
  6: '周六',
  0: '周日',
  7: '周日',
};

const pad2 = (n: number): string =>
  String(Math.max(0, Math.floor(Number.isNaN(n) ? 0 : n))).padStart(2, '0');

export function parseHourMinute(
  raw: string | undefined,
  defaultHour: number,
  defaultMinute = 0,
): [number, number] {
  if (!raw || typeof raw !== 'string') {
    return [defaultHour, defaultMinute];
  }
  const match = raw.match(/(\d{1,2}):(\d{1,2})/);
  if (!match) {
    return [defaultHour, defaultMinute];
  }
  const h = Number(match[1]);
  const m = Number(match[2]);
  if (Number.isNaN(h) || Number.isNaN(m)) {
    return [defaultHour, defaultMinute];
  }
  return [Math.min(23, Math.max(0, h)), Math.min(59, Math.max(0, m))];
}

export function formatDurationMinutes(minutes: number): string {
  const total = Math.max(0, Math.round(minutes || 0));
  const hours = Math.floor(total / 60);
  const mins = total % 60;
  if (hours > 0 && mins > 0) {
    return `${hours}小时${mins}分钟`;
  }
  if (hours > 0) {
    return `${hours}小时`;
  }
  return `${mins}分钟`;
}

function parseCronFieldList(field: string, minVal: number, maxVal: number): number[] {
  if (!field || field === '*') return [];
  const result = new Set<number>();
  for (const part of field.split(',')) {
    const trimmed = part.trim();
    if (trimmed.includes('-')) {
      const [startStr, endStr] = trimmed.split('-');
      const start = Number(startStr);
      const end = Number(endStr);
      if (!Number.isNaN(start) && !Number.isNaN(end) && start <= end) {
        for (let i = Math.max(minVal, start); i <= Math.min(maxVal, end); i += 1) {
          result.add(i === 0 ? 7 : i);
        }
      }
    } else {
      const num = Number(trimmed);
      if (!Number.isNaN(num) && num >= minVal && num <= maxVal) {
        result.add(num === 0 && maxVal === 7 ? 7 : num);
      }
    }
  }
  return Array.from(result).sort((a, b) => a - b);
}

function formatWeekdaysLabel(weekdays: number[]): string {
  const normalized = Array.from(new Set(weekdays.map((d) => (d === 0 ? 7 : d)))).sort(
    (a, b) => a - b,
  );
  if (normalized.length === 0 || normalized.length === 7) {
    return '每天';
  }
  if (normalized.join(',') === '1,2,3,4,5') {
    return '周一至周五';
  }
  if (normalized.join(',') === '1,2,3,4,5,6') {
    return '周一至周六';
  }
  if (normalized.join(',') === '6,7') {
    return '周六、周日';
  }
  return normalized.map((d) => WEEKDAY_NAMES[d] || `周${d}`).join('、');
}

export function parseCronScheduleItem(
  cronExpr: string,
  durationMinutes: number,
): VisualScheduleSlot {
  const parts = (cronExpr || '0 8 * * *').trim().split(/\s+/);
  const minPart = Number(parts[0]);
  const hourPart = Number(parts[1]);
  const domPart = parts[2] || '*';
  const dowPart = parts[4] || '*';

  const startHour = Number.isNaN(hourPart) ? 8 : Math.min(23, Math.max(0, hourPart));
  const startMin = Number.isNaN(minPart) ? 0 : Math.min(59, Math.max(0, minPart));
  const safeDuration = Math.max(1, Math.round(durationMinutes || 60));

  const startTotalMinutes = startHour * 60 + startMin;
  const endTotalMinutes = startTotalMinutes + safeDuration;
  const isNextDay = endTotalMinutes > 24 * 60;
  const normalizedEndMinutes = endTotalMinutes % (24 * 60);
  const endHour = Math.floor(normalizedEndMinutes / 60);
  const endMin = normalizedEndMinutes % 60;

  const startTime = `${pad2(startHour)}:${pad2(startMin)}`;
  const endTime =
    endTotalMinutes === 24 * 60
      ? '24:00'
      : `${pad2(endHour)}:${pad2(endMin)}`;

  let cycleType: ScheduleCycleType = 'DAILY';
  let weekdays: number[] = [];
  let monthDays: number[] = [];
  let cycleLabel = '每天';

  if (dowPart !== '*' && dowPart !== '?') {
    cycleType = 'WEEKLY';
    weekdays = parseCronFieldList(dowPart, 0, 7);
    cycleLabel = formatWeekdaysLabel(weekdays);
  } else if (domPart !== '*' && domPart !== '?') {
    cycleType = 'MONTHLY';
    monthDays = parseCronFieldList(domPart, 1, 31);
    cycleLabel =
      monthDays.length > 0
        ? `每月 ${monthDays.map((d) => `${d}日`).join('、')}`
        : '每天';
  }

  const timeRangeLabel = isNextDay
    ? `${startTime} - 次日 ${endTime}`
    : `${startTime} - ${endTime}`;
  const durationLabel = formatDurationMinutes(safeDuration);
  const summaryLabel = `${cycleLabel} ${timeRangeLabel} (${durationLabel})`;

  return {
    cycleType,
    weekdays,
    monthDays,
    startTime,
    endTime: endTime === '24:00' ? '00:00' : endTime,
    durationMinutes: safeDuration,
    isNextDay: isNextDay || endTime === '24:00',
    cycleLabel,
    timeRangeLabel,
    durationLabel,
    summaryLabel,
  };
}

export function calculateDurationFromTimeRange(
  startTime: string,
  endTime: string,
): { durationMinutes: number; isNextDay: boolean; timeRangeLabel: string } {
  const [sh, sm] = parseHourMinute(startTime, 8, 0);
  const [eh, em] = parseHourMinute(endTime, 12, 0);
  const startTotal = sh * 60 + sm;
  const endTotal = eh * 60 + em;

  let durationMinutes = endTotal - startTotal;
  let isNextDay = false;
  if (durationMinutes <= 0) {
    durationMinutes = 24 * 60 - startTotal + endTotal;
    isNextDay = true;
  }

  const displayEnd =
    endTotal === 0 && isNextDay && startTotal > 0 ? '24:00' : `${pad2(eh)}:${pad2(em)}`;
  const timeRangeLabel =
    isNextDay && displayEnd !== '24:00'
      ? `${pad2(sh)}:${pad2(sm)} - 次日 ${displayEnd}`
      : `${pad2(sh)}:${pad2(sm)} - ${displayEnd}`;

  return { durationMinutes, isNextDay, timeRangeLabel };
}

export function buildCronFromVisualSlot(input: {
  cycleType: ScheduleCycleType;
  weekdays?: number[];
  monthDays?: number[];
  startTime: string;
  endTime: string;
}): { cron_expr: string; duration_minutes: number } {
  const [hour, minute] = parseHourMinute(input.startTime, 8, 0);

  let dom = '*';
  let dow = '*';

  if (input.cycleType === 'WEEKLY' && input.weekdays && input.weekdays.length > 0) {
    const sorted = Array.from(new Set(input.weekdays)).sort((a, b) => a - b);
    dow = sorted.join(',');
  } else if (input.cycleType === 'MONTHLY' && input.monthDays && input.monthDays.length > 0) {
    const sorted = Array.from(new Set(input.monthDays)).sort((a, b) => a - b);
    dom = sorted.join(',');
  }

  const { durationMinutes } = calculateDurationFromTimeRange(input.startTime, input.endTime);

  return {
    cron_expr: `${minute} ${hour} ${dom} * ${dow}`,
    duration_minutes: durationMinutes,
  };
}

export async function queryOperationSchedules(
  params: Record<string, any> = {},
  sort: SortParams = {},
): Promise<PagedResult<DeviceOperationSchedule>> {
  return requestPagedList<DeviceOperationSchedule>('/api/v1/operation-schedules', {
    params,
    sort,
    defaultPageSize: 20,
  });
}

export async function listAllOperationSchedules(activeOnly = true) {
  return requestAllListItems<DeviceOperationSchedule>(
    '/api/v1/operation-schedules',
    activeOnly ? { status: 1 } : {},
    100,
  );
}

export async function createOperationSchedule(payload: DeviceOperationSchedulePayload) {
  return request<DeviceOperationSchedule>('/api/v1/operation-schedules', {
    method: 'POST',
    data: payload,
  });
}

export async function updateOperationSchedule(
  id: string,
  payload: Partial<DeviceOperationSchedulePayload>,
) {
  return request<DeviceOperationSchedule>(`/api/v1/operation-schedules/${id}`, {
    method: 'PUT',
    data: payload,
  });
}

export async function deleteOperationSchedule(id: string) {
  return request<{ message: string }>(`/api/v1/operation-schedules/${id}`, {
    method: 'DELETE',
  });
}

export async function getOperationScheduleItems(scheduleId: string) {
  return (
    (await request<DeviceOperationScheduleItem[]>(
      `/api/v1/operation-schedules/${scheduleId}/items`,
      {
        method: 'GET',
      },
    )) || []
  );
}

export async function updateOperationScheduleItems(
  scheduleId: string,
  items: DeviceOperationScheduleItemPayload[],
) {
  return request<DeviceOperationScheduleItem[]>(
    `/api/v1/operation-schedules/${scheduleId}/items`,
    {
      method: 'PUT',
      data: { items },
    },
  );
}
