import { request } from '@umijs/max';

type JsonRecord = Record<string, any>;

export type DiagnosisDetailStatus =
  | 'pending'
  | 'complete'
  | 'unavailable'
  | 'legacy_partial';

export type DiagnosisReportSummary = {
  report_id: string;
  diagnosed_at: string | null;
  sampled_at: string | null;
  overall_level: number | null;
  overall_label: string | null;
};

export type DiagnosisDeviceSummary = {
  id: string;
  code: string | null;
  name: string | null;
  category: string | null;
  process: string | null;
  location: string | null;
};

export type DiagnosisRuleCheck = {
  key: string;
  label: string;
  actual: string | number | null;
  comparator: string | null;
  threshold: string | number | null;
  triggered: boolean | null;
  unit: string | null;
  summary: string | null;
};

export type DiagnosisTrendPoint = {
  sampled_at: string;
  value: number | null;
  threshold: number | null;
  upper_threshold: number | null;
  lower_threshold: number | null;
};

export type DiagnosisTrendSeries = {
  key: string;
  label: string;
  unit: string | null;
  points: DiagnosisTrendPoint[];
};

export type DiagnosisTrend = {
  status: DiagnosisDetailStatus;
  note: string | null;
  series: DiagnosisTrendSeries[];
};

export type DiagnosisAttempt = {
  id: string;
  report_id: string | null;
  phase: string | null;
  sequence: number | null;
  result_status: string | null;
  fault_level: number | null;
  level_label: string | null;
  description: string | null;
  diagnosed_at: string | null;
  rms: number | null;
  confirmation_status: string | null;
};

export type DiagnosisFault = {
  case_id: string;
  fault_type: string;
  fault_label: string;
  level: number | null;
  level_label: string | null;
  summary: string | null;
  status: DiagnosisDetailStatus;
  evidence_schema_version: number | null;
  checks: DiagnosisRuleCheck[];
  trend: DiagnosisTrend | null;
  attempts: DiagnosisAttempt[];
};

export type DiagnosisReportDetail = {
  report: DiagnosisReportSummary;
  device: DiagnosisDeviceSummary;
  faults: DiagnosisFault[];
  provenance: {
    thresholds: string | null;
    trend_series: string | null;
  };
};

const LEVEL_LABELS: Record<number, string> = {
  0: '正常',
  1: '关注',
  2: '异常',
  3: '告警',
  4: '危险',
};

function getField<T>(record: JsonRecord | null | undefined, ...keys: string[]): T | undefined {
  if (!record) {
    return undefined;
  }
  for (const key of keys) {
    if (Object.prototype.hasOwnProperty.call(record, key) && record[key] !== undefined) {
      return record[key] as T;
    }
  }
  return undefined;
}

function toStringValue(value: unknown): string | null {
  if (value === null || value === undefined || value === '') {
    return null;
  }
  return String(value);
}

function toNumberValue(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return null;
}

function toBooleanValue(value: unknown): boolean | null {
  if (typeof value === 'boolean') {
    return value;
  }
  return null;
}

function toArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

function normalizeStatus(value: unknown): DiagnosisDetailStatus {
  const normalized = String(value || '').trim().toLowerCase();
  switch (normalized) {
    case 'pending':
      return 'pending';
    case 'complete':
    case 'available':
    case 'ready':
      return 'complete';
    case 'legacy_partial':
      return 'legacy_partial';
    default:
      return 'unavailable';
  }
}

function levelLabel(level: unknown, fallback?: string | null) {
  const numeric = toNumberValue(level);
  if (numeric !== null && LEVEL_LABELS[numeric]) {
    return LEVEL_LABELS[numeric];
  }
  return toStringValue(fallback);
}

function normalizeCheck(item: JsonRecord, index: number): DiagnosisRuleCheck {
  return {
    key: toStringValue(getField(item, 'key', 'code', 'rule_code')) || `check-${index}`,
    label:
      toStringValue(getField(item, 'label', 'name', 'rule_label', 'rule_code')) ||
      `规则 ${index + 1}`,
    actual:
      getField(
        item,
        'actual',
        'actual_value',
        'current',
        'value',
        'observed',
        'observed_value',
      ) ?? null,
    comparator: toStringValue(getField(item, 'comparator', 'operator', 'comparison')),
    threshold:
      getField(item, 'threshold', 'threshold_value', 'limit', 'baseline', 'expected') ?? null,
    triggered: toBooleanValue(getField(item, 'triggered', 'matched', 'hit')),
    unit: toStringValue(getField(item, 'unit')),
    summary: toStringValue(getField(item, 'summary', 'description', 'detail')),
  };
}

function normalizeTrendPoint(item: JsonRecord): DiagnosisTrendPoint | null {
  const sampledAt = toStringValue(getField(item, 'sampled_at', 'sampledAt', 'ts', 'time', 'timestamp'));
  if (!sampledAt) {
    return null;
  }
  return {
    sampled_at: sampledAt,
    value: toNumberValue(getField(item, 'value', 'actual', 'current')),
    threshold: toNumberValue(getField(item, 'threshold')),
    upper_threshold: toNumberValue(getField(item, 'upper_threshold', 'upperThreshold')),
    lower_threshold: toNumberValue(getField(item, 'lower_threshold', 'lowerThreshold')),
  };
}

function normalizeTrendSeries(item: JsonRecord, index: number): DiagnosisTrendSeries {
  const rawPoints = toArray<JsonRecord>(getField(item, 'points', 'samples', 'data'));
  const points = rawPoints
    .map((point) => normalizeTrendPoint(point))
    .filter((point): point is DiagnosisTrendPoint => Boolean(point));
  return {
    key: toStringValue(getField(item, 'key', 'name', 'label')) || `series-${index}`,
    label:
      toStringValue(getField(item, 'label', 'name', 'window_label', 'window')) ||
      `趋势 ${index + 1}`,
    unit: toStringValue(getField(item, 'unit')),
    points,
  };
}

function normalizeTrend(rawTrend: JsonRecord | null | undefined): DiagnosisTrend | null {
  if (!rawTrend) {
    return null;
  }
  return {
    status: normalizeStatus(getField(rawTrend, 'status')),
    note: toStringValue(getField(rawTrend, 'note', 'summary', 'description')),
    series: toArray<JsonRecord>(getField(rawTrend, 'series')).map((item, index) =>
      normalizeTrendSeries(item, index),
    ),
  };
}

function normalizeAttempt(item: JsonRecord, index: number): DiagnosisAttempt {
  const level = getField(item, 'fault_level', 'level');
  return {
    id: toStringValue(getField(item, 'id')) || `attempt-${index}`,
    report_id: toStringValue(getField(item, 'report_id', 'reportId')),
    phase: toStringValue(getField(item, 'phase')),
    sequence: toNumberValue(getField(item, 'sequence')),
    result_status: toStringValue(getField(item, 'result_status', 'resultStatus')),
    fault_level: toNumberValue(level),
    level_label: levelLabel(level, toStringValue(getField(item, 'level_label', 'levelLabel'))),
    description: toStringValue(getField(item, 'description', 'summary')),
    diagnosed_at: toStringValue(getField(item, 'diagnosed_at', 'diagnosedAt', 'sampled_at', 'sampledAt')),
    rms: toNumberValue(getField(item, 'rms', 'rms_m', 'rms_value')),
    confirmation_status: toStringValue(getField(item, 'confirmation_status', 'confirmationStatus')),
  };
}

function inferFaultStatus(rawFault: JsonRecord, trend: DiagnosisTrend | null): DiagnosisDetailStatus {
  const explicitStatus = getField(rawFault, 'status', 'detail_status', 'case_status');
  if (explicitStatus !== undefined && explicitStatus !== null && explicitStatus !== '') {
    return normalizeStatus(explicitStatus);
  }
  if (trend?.status) {
    return trend.status;
  }
  if (toArray(getField(rawFault, 'checks')).length || toArray(getField(rawFault, 'attempts')).length) {
    return 'complete';
  }
  return 'unavailable';
}

function normalizeFault(item: JsonRecord, index: number): DiagnosisFault {
  const trend = normalizeTrend(getField(item, 'trend'));
  const level = getField(item, 'level', 'fault_level');
  return {
    case_id: toStringValue(getField(item, 'case_id', 'caseId')) || `fault-${index}`,
    fault_type: toStringValue(getField(item, 'fault_type', 'faultType')) || `fault-${index}`,
    fault_label:
      toStringValue(getField(item, 'fault_label', 'faultLabel')) ||
      (toStringValue(getField(item, 'fault_type', 'faultType')) === 'temperature' ? '温度' : '振动'),
    level: toNumberValue(level),
    level_label: levelLabel(level, toStringValue(getField(item, 'level_label', 'levelLabel'))),
    summary: toStringValue(getField(item, 'summary', 'description')),
    status: inferFaultStatus(item, trend),
    evidence_schema_version: toNumberValue(getField(item, 'evidence_schema_version', 'evidenceSchemaVersion')),
    checks: toArray<JsonRecord>(getField(item, 'checks')).map((check, checkIndex) =>
      normalizeCheck(check, checkIndex),
    ),
    trend,
    attempts: toArray<JsonRecord>(getField(item, 'attempts')).map((attempt, attemptIndex) =>
      normalizeAttempt(attempt, attemptIndex),
    ),
  };
}

export function normalizeDiagnosisReportDetail(payload: JsonRecord): DiagnosisReportDetail {
  const report = (getField<JsonRecord>(payload, 'report') || {}) as JsonRecord;
  const device = (getField<JsonRecord>(payload, 'device') || {}) as JsonRecord;
  const provenance = (getField<JsonRecord>(payload, 'provenance') || {}) as JsonRecord;
  const overallLevel = getField(report, 'overall_level', 'overallLevel');

  return {
    report: {
      report_id: toStringValue(getField(report, 'report_id', 'reportId')) || '',
      diagnosed_at: toStringValue(getField(report, 'diagnosed_at', 'diagnosedAt')),
      sampled_at: toStringValue(getField(report, 'sampled_at', 'sampledAt')),
      overall_level: toNumberValue(overallLevel),
      overall_label: levelLabel(overallLevel, toStringValue(getField(report, 'overall_label', 'overallLabel'))),
    },
    device: {
      id: toStringValue(getField(device, 'id')) || '',
      code: toStringValue(getField(device, 'code')),
      name: toStringValue(getField(device, 'name')),
      category: toStringValue(getField(device, 'category')),
      process: toStringValue(getField(device, 'process')),
      location: toStringValue(getField(device, 'location')),
    },
    faults: toArray<JsonRecord>(getField(payload, 'faults')).map((fault, index) =>
      normalizeFault(fault, index),
    ),
    provenance: {
      thresholds: toStringValue(getField(provenance, 'thresholds')),
      trend_series: toStringValue(getField(provenance, 'trend_series', 'trendSeries')),
    },
  };
}

export async function getWxDiagnosisDetail(reportId: string) {
  const response = await request<JsonRecord>(`/api/v1/wx/diagnosis/reports/${reportId}`, {
    method: 'GET',
    credentials: 'include',
  });
  return normalizeDiagnosisReportDetail(response || {});
}

export async function getDiagnosisDetail(reportId: string) {
  const response = await request<JsonRecord>(`/api/v1/diagnosis/reports/${reportId}/detail`, {
    method: 'GET',
  });
  return normalizeDiagnosisReportDetail(response || {});
}
