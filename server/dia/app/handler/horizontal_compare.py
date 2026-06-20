"""
Horizontal peer comparison helpers.

The relational peer group comes from DiagnosisContextService and is cached in
Redis. This module only reads that context and fetches the latest comparable
feature values for the peer sensors from InfluxDB.
"""

from dataclasses import dataclass
from statistics import median
from typing import Any

from app.handler.vibration_common import (
    LEVEL_ATTENTION,
    LEVEL_NORMAL,
    LEVEL_NOT_CHECKED,
    LEVEL_SEVERE,
    LEVEL_WARNING,
    DiagnosisItemConclusion,
    format_value,
)

MEASUREMENT = "vibration_feature"
MIN_PEER_COUNT = 1


@dataclass(frozen=True)
class PeerThresholds:
    relative_attention: float | None = None
    relative_warning: float | None = None
    relative_severe: float | None = None
    absolute_attention: float | None = None
    absolute_warning: float | None = None
    absolute_severe: float | None = None
    absolute_mode: bool = False


@dataclass(frozen=True)
class PeerComparisonResult:
    enabled: bool
    enough_data: bool
    reason: str | None
    field: str
    axis: str | None
    current_value: float | None
    peer_count: int
    peer_median: float | None
    delta: float | None
    relative_delta: float | None
    level: str | None


def compare_peer_value(
    *,
    current_sn: str,
    current_value: float | None,
    context: dict[str, Any] | None,
    field: str,
    thresholds: PeerThresholds,
    axis: str | None = None,
    same_direction: bool = False,
) -> PeerComparisonResult:
    if current_value is None:
        return PeerComparisonResult(
            enabled=False,
            enough_data=False,
            reason="missing_current_value",
            field=field,
            axis=axis,
            current_value=None,
            peer_count=0,
            peer_median=None,
            delta=None,
            relative_delta=None,
            level=None,
        )

    peer_group = (context or {}).get("peer_group")
    if not isinstance(peer_group, dict) or not peer_group.get("enabled"):
        return PeerComparisonResult(
            enabled=False,
            enough_data=False,
            reason=(peer_group or {}).get("reason") if isinstance(peer_group, dict) else "peer_group_missing",
            field=field,
            axis=axis,
            current_value=current_value,
            peer_count=0,
            peer_median=None,
            delta=None,
            relative_delta=None,
            level=None,
        )

    peer_sns = _peer_sns(current_sn=current_sn, context=context, same_direction=same_direction)
    if len(peer_sns) < MIN_PEER_COUNT:
        return PeerComparisonResult(
            enabled=True,
            enough_data=False,
            reason="not_enough_peer_sensors",
            field=field,
            axis=axis,
            current_value=current_value,
            peer_count=len(peer_sns),
            peer_median=None,
            delta=None,
            relative_delta=None,
            level=None,
        )

    peer_values = _query_latest_peer_values(peer_sns, field=field, axis=axis)
    peer_values = [value for value in peer_values if value is not None]
    if len(peer_values) < MIN_PEER_COUNT:
        return PeerComparisonResult(
            enabled=True,
            enough_data=False,
            reason="not_enough_peer_values",
            field=field,
            axis=axis,
            current_value=current_value,
            peer_count=len(peer_values),
            peer_median=None,
            delta=None,
            relative_delta=None,
            level=None,
        )

    peer_median = float(median(peer_values))
    delta = current_value - peer_median
    relative_delta = delta / peer_median if peer_median > 0 else None
    level = _peer_level(delta, relative_delta, thresholds)
    return PeerComparisonResult(
        enabled=True,
        enough_data=True,
        reason=None,
        field=field,
        axis=axis,
        current_value=current_value,
        peer_count=len(peer_values),
        peer_median=peer_median,
        delta=delta,
        relative_delta=relative_delta,
        level=level,
    )


def build_peer_item_conclusion(
    *,
    result: PeerComparisonResult,
    name: str,
    normal_text: str,
    warning_text: str,
    thresholds: PeerThresholds,
) -> DiagnosisItemConclusion:
    evidence = _peer_evidence(result, thresholds)
    if not result.enabled or not result.enough_data:
        return DiagnosisItemConclusion(
            name=name,
            level=LEVEL_NOT_CHECKED,
            triggered=False,
            conclusion=f"{name}横向比较数据不足",
            evidence=evidence,
        )

    if result.level is None:
        return DiagnosisItemConclusion(
            name=name,
            level=LEVEL_NORMAL,
            triggered=False,
            conclusion=normal_text,
            evidence=[*evidence, "rule=peer_delta below attention threshold"],
        )

    return DiagnosisItemConclusion(
        name=name,
        level=result.level,
        triggered=True,
        conclusion=f"{warning_text}，达到{result.level}范围",
        evidence=[*evidence, "rule=peer_delta >= level threshold"],
    )


def _peer_sns(
    *,
    current_sn: str,
    context: dict[str, Any] | None,
    same_direction: bool,
) -> list[str]:
    peer_group = ((context or {}).get("peer_group") or {})
    members = peer_group.get("members")
    if not isinstance(members, list):
        return []

    current_direction = (((context or {}).get("monitoring") or {}).get("direction"))
    sns: list[str] = []
    for member in members:
        if not isinstance(member, dict):
            continue
        monitoring = member.get("monitoring")
        sensor = member.get("sensor")
        if not isinstance(monitoring, dict) or not isinstance(sensor, dict):
            continue
        if same_direction and monitoring.get("direction") != current_direction:
            continue
        sn = sensor.get("sn")
        if isinstance(sn, str) and sn and sn != current_sn:
            sns.append(sn)
    return sorted(set(sns))


def _query_latest_peer_values(peer_sns: list[str], *, field: str, axis: str | None) -> list[float]:
    if not peer_sns:
        return []
    try:
        tables = _query_influx(_build_latest_peer_query(peer_sns, field=field, axis=axis))
    except Exception:
        return []

    values: list[float] = []
    for table in tables:
        for record in getattr(table, "records", []):
            value = _record_value(record)
            if isinstance(value, bool) or value is None:
                continue
            if isinstance(value, (int, float)):
                values.append(float(value))
    return values


def _build_latest_peer_query(peer_sns: list[str], *, field: str, axis: str | None) -> str:
    from app.config import settings

    escaped_bucket = _escape_flux_string(settings.influx_bucket)
    sn_values = ", ".join(f'"{_escape_flux_string(sn)}"' for sn in peer_sns)
    axis_filter = f'|> filter(fn: (r) => r.axis == "{_escape_flux_string(axis)}")' if axis else ""
    return f'''
        from(bucket:"{escaped_bucket}")
            |> range(start: 0)
            |> filter(fn: (r) => r._measurement == "{MEASUREMENT}")
            |> filter(fn: (r) => contains(value: r.sn, set: [{sn_values}]))
            |> filter(fn: (r) => r.sample_type == "normal")
            |> filter(fn: (r) => r._field == "{_escape_flux_string(field)}")
            {axis_filter}
            |> group(columns: ["sn"])
            |> sort(columns: ["_time"], desc: true)
            |> first()
    '''


def _query_influx(query: str) -> Any:
    from app.config import settings
    from app.database import influxdb_manager

    client = influxdb_manager.get_client()
    query_api = client.query_api()
    return query_api.query(org=settings.influx_org, query=query)


def _record_value(record: Any) -> Any:
    if hasattr(record, "get_value"):
        return record.get_value()
    values = getattr(record, "values", None)
    if isinstance(values, dict):
        return values.get("_value")
    return None


def _peer_level(delta: float, relative_delta: float | None, thresholds: PeerThresholds) -> str | None:
    compare_delta = abs(delta) if thresholds.absolute_mode else delta
    compare_relative = (
        abs(relative_delta)
        if thresholds.absolute_mode and relative_delta is not None
        else relative_delta
    )

    if _threshold_hit(compare_delta, compare_relative, thresholds.absolute_severe, thresholds.relative_severe):
        return LEVEL_SEVERE
    if _threshold_hit(compare_delta, compare_relative, thresholds.absolute_warning, thresholds.relative_warning):
        return LEVEL_WARNING
    if _threshold_hit(compare_delta, compare_relative, thresholds.absolute_attention, thresholds.relative_attention):
        return LEVEL_ATTENTION
    return None


def _threshold_hit(
    delta: float,
    relative_delta: float | None,
    absolute_threshold: float | None,
    relative_threshold: float | None,
) -> bool:
    if absolute_threshold is None and relative_threshold is None:
        return False
    if absolute_threshold is not None and delta < absolute_threshold:
        return False
    if relative_threshold is not None:
        if relative_delta is None or relative_delta < relative_threshold:
            return False
    return True


def _peer_evidence(result: PeerComparisonResult, thresholds: PeerThresholds) -> list[str]:
    return [
        f"field={result.field}",
        f"axis={result.axis or 'N/A'}",
        f"enabled={result.enabled}",
        f"enough_data={result.enough_data}",
        f"reason={result.reason or 'N/A'}",
        f"current_value={format_value(result.current_value)}",
        f"peer_count={result.peer_count}",
        f"peer_median={format_value(result.peer_median)}",
        f"delta={format_value(result.delta)}",
        f"relative_delta={format_value(result.relative_delta)}",
        f"relative_attention={format_value(thresholds.relative_attention)}",
        f"relative_warning={format_value(thresholds.relative_warning)}",
        f"relative_severe={format_value(thresholds.relative_severe)}",
        f"absolute_attention={format_value(thresholds.absolute_attention)}",
        f"absolute_warning={format_value(thresholds.absolute_warning)}",
        f"absolute_severe={format_value(thresholds.absolute_severe)}",
        f"absolute_mode={thresholds.absolute_mode}",
    ]


def _escape_flux_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
