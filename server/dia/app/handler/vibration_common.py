"""
Shared helpers for vibration-related diagnosis modules.
"""

from dataclasses import dataclass
from decimal import Decimal
from numbers import Real
from typing import Any

AXES = ("X", "Y", "Z")
MEASUREMENT = "vibration_feature"
HISTORY_WINDOW_SIZE = 72
SHORT_WINDOW_SIZE = 6

LEVEL_NOT_CHECKED = "未检测"
LEVEL_NORMAL = "正常"
LEVEL_ATTENTION = "关注"
LEVEL_WARNING = "警告"
LEVEL_SEVERE = "严重"
CONCLUSION_LEVEL_ORDER = {
    LEVEL_NORMAL: 0,
    LEVEL_ATTENTION: 1,
    LEVEL_WARNING: 2,
    LEVEL_SEVERE: 3,
}


@dataclass(frozen=True)
class DiagnosisItemConclusion:
    name: str
    level: str
    triggered: bool
    conclusion: str
    evidence: list[str]


@dataclass(frozen=True)
class DiagnosisConclusion:
    level: str
    triggered: bool
    conclusion: str
    evidence: list[str]
    items: list[DiagnosisItemConclusion]


@dataclass(frozen=True)
class MetricDiagnosisResult:
    sn: str
    report_id: str
    metric: str
    conclusion: DiagnosisConclusion


@dataclass(frozen=True)
class AxisFeaturePoint:
    report_id: str
    axis: str
    sort_key: Any
    fields: dict[str, float]


def skipped_result(
    *,
    metric: str,
    sn: str,
    report_id: str,
    reason: str,
    evidence: list[str],
) -> MetricDiagnosisResult:
    item = DiagnosisItemConclusion(
        name="诊断前置条件",
        level=LEVEL_NOT_CHECKED,
        triggered=False,
        conclusion=reason,
        evidence=evidence,
    )
    return MetricDiagnosisResult(
        sn=sn,
        report_id=report_id,
        metric=metric,
        conclusion=DiagnosisConclusion(
            level=LEVEL_NOT_CHECKED,
            triggered=False,
            conclusion=f"{metric} 诊断结论：未检测，{reason}",
            evidence=evidence,
            items=[item],
        ),
    )


def build_metric_conclusion(metric_label: str, items: list[DiagnosisItemConclusion]) -> DiagnosisConclusion:
    level = highest_level(items)
    triggered_items = [item for item in items if item.triggered]
    evidence = [entry for item in items for entry in item.evidence]
    if not triggered_items:
        if all(item.level == LEVEL_NOT_CHECKED for item in items):
            return DiagnosisConclusion(
                level=LEVEL_NOT_CHECKED,
                triggered=False,
                conclusion=f"{metric_label}诊断结论：未检测",
                evidence=evidence,
                items=items,
            )
        return DiagnosisConclusion(
            level=LEVEL_NORMAL,
            triggered=False,
            conclusion=f"{metric_label}诊断结论：正常",
            evidence=evidence,
            items=items,
        )

    reasons = "；".join(item.conclusion for item in triggered_items)
    return DiagnosisConclusion(
        level=level,
        triggered=True,
        conclusion=f"{metric_label}诊断结论：{level}，{reasons}",
        evidence=evidence,
        items=items,
    )


def highest_level(items: list[DiagnosisItemConclusion]) -> str:
    checked = [item.level for item in items if item.level != LEVEL_NOT_CHECKED]
    if not checked:
        return LEVEL_NOT_CHECKED
    return max(checked, key=lambda level: CONCLUSION_LEVEL_ORDER.get(level, 0))


def axis_label(axis: str, context: dict[str, Any] | None = None) -> str:
    direction = (((context or {}).get("monitoring") or {}).get("direction"))
    labels = {
        "vertical": {"X": "X轴(水平)", "Y": "Y轴(轴向)", "Z": "Z轴(垂直)"},
        "horizontal": {"X": "X轴(垂直)", "Y": "Y轴(轴向)", "Z": "Z轴(水平)"},
        "axial": {"X": "X轴(垂直)", "Y": "Y轴(水平)", "Z": "Z轴(轴向)"},
    }
    return labels.get(str(direction), {}).get(axis, f"{axis}轴")


def is_normal_sample(payload: dict[str, Any]) -> bool:
    return payload.get("sample_type") == "normal"


def axis_payload(payload: dict[str, Any], axis: str) -> dict[str, Any] | None:
    axis_features = payload.get("axis_features")
    if not isinstance(axis_features, dict):
        return None
    value = axis_features.get(axis)
    return value if isinstance(value, dict) else None


def time_feature(payload: dict[str, Any], axis: str, name: str) -> float | None:
    axis_data = axis_payload(payload, axis)
    if not axis_data:
        return None
    time_data = axis_data.get("time")
    if not isinstance(time_data, dict):
        return None
    return as_float(time_data.get(name))


def band_feature(payload: dict[str, Any], axis: str, name: str) -> float | None:
    axis_data = axis_payload(payload, axis)
    if not axis_data:
        return None
    band_data = axis_data.get("band_energy_ratio")
    if not isinstance(band_data, dict):
        return None
    return as_float(band_data.get(name))


def freq_feature(payload: dict[str, Any], axis: str, name: str) -> float | None:
    axis_data = axis_payload(payload, axis)
    if not axis_data:
        return None
    freq_data = axis_data.get("freq")
    if not isinstance(freq_data, dict):
        return None
    return as_float(freq_data.get(name))


def peak_features(payload: dict[str, Any], axis: str) -> list[dict[str, float]]:
    axis_data = axis_payload(payload, axis)
    if not axis_data:
        return []
    freq_data = axis_data.get("freq")
    if not isinstance(freq_data, dict):
        return []
    peaks = freq_data.get("peaks")
    if not isinstance(peaks, list):
        return []
    values = []
    for peak in peaks:
        if not isinstance(peak, dict):
            continue
        freq_hz = as_float(peak.get("freq_hz"))
        amp_g = as_float(peak.get("amp_g"))
        if freq_hz is not None and amp_g is not None:
            values.append({"freq_hz": freq_hz, "amp_g": amp_g})
    return values


def as_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (Real, Decimal)):
        return float(value)
    return None


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def relative_delta(current: float, baseline: float | None) -> float | None:
    if baseline is None or baseline <= 0:
        return None
    return (current - baseline) / baseline


def level_from_ratio(ratio: float | None, attention: float, warning: float, severe: float) -> str | None:
    if ratio is None:
        return None
    if ratio >= severe:
        return LEVEL_SEVERE
    if ratio >= warning:
        return LEVEL_WARNING
    if ratio >= attention:
        return LEVEL_ATTENTION
    return None


def format_value(value: Any, digits: int = 4) -> str:
    if isinstance(value, float):
        return f"{value:.{digits}g}"
    return str(value)


def load_recent_axis_feature_points(
    sn: str,
    fields: list[str],
    limit: int = HISTORY_WINDOW_SIZE,
) -> list[AxisFeaturePoint]:
    """Load recent unique report/axis feature rows from InfluxDB."""
    if not fields:
        return []
    try:
        tables = _query_influx(_build_recent_feature_query(sn, fields, limit))
        return _extract_axis_feature_points(tables)
    except Exception:
        return []


def _build_recent_feature_query(sn: str, fields: list[str], limit: int) -> str:
    from app.config import settings

    escaped_sn = _escape_flux_string(sn)
    escaped_bucket = _escape_flux_string(settings.influx_bucket)
    field_filters = " or ".join([f'r._field == "{_escape_flux_string(field)}"' for field in fields])
    row_limit = max(limit * len(AXES), len(AXES))
    return f'''
        from(bucket:"{escaped_bucket}")
            |> range(start: 0)
            |> filter(fn: (r) => r._measurement == "{MEASUREMENT}")
            |> filter(fn: (r) => r.sn == "{escaped_sn}")
            |> filter(fn: (r) => r.sample_type == "normal")
            |> filter(fn: (r) => {field_filters})
            |> pivot(rowKey: ["_time", "report_id", "axis"], columnKey: ["_field"], valueColumn: "_value")
            |> group()
            |> sort(columns: ["_time"], desc: true)
            |> limit(n: {row_limit})
    '''


def _query_influx(query: str) -> Any:
    from app.config import settings
    from app.database import influxdb_manager

    client = influxdb_manager.get_client()
    query_api = client.query_api()
    return query_api.query(org=settings.influx_org, query=query)


def _extract_axis_feature_points(tables: Any) -> list[AxisFeaturePoint]:
    points: list[AxisFeaturePoint] = []
    seen: set[tuple[str, str]] = set()
    for table in tables:
        for record in getattr(table, "records", []):
            values = getattr(record, "values", None)
            if not isinstance(values, dict):
                continue
            report_id = values.get("report_id")
            axis = values.get("axis")
            if not isinstance(report_id, str) or axis not in AXES:
                continue
            key = (report_id, axis)
            if key in seen:
                continue
            fields = {
                name: float(value)
                for name, value in values.items()
                if name not in {"result", "table", "_start", "_stop", "_time", "report_id", "axis", "sn"}
                and as_float(value) is not None
            }
            points.append(
                AxisFeaturePoint(
                    report_id=report_id,
                    axis=axis,
                    sort_key=_record_sort_key(record, values),
                    fields=fields,
                )
            )
            seen.add(key)
    return sorted(points, key=lambda point: _sort_key_to_ms(point.sort_key))


def _record_sort_key(record: Any, values: dict[str, Any]) -> Any:
    if hasattr(record, "get_time"):
        value = record.get_time()
        if value is not None:
            return value
    return values.get("_time")


def _sort_key_to_ms(value: Any) -> int:
    if hasattr(value, "timestamp"):
        return int(value.timestamp() * 1000)
    if isinstance(value, str):
        try:
            from datetime import datetime

            return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)
        except ValueError:
            return 0
    return 0


def _escape_flux_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
