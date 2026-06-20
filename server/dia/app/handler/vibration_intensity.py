"""
Vibration intensity diagnosis.

This module evaluates overall vibration severity. The primary field is
`rms_vel_mm_s`; acceleration and peak fields are retained as evidence.
"""

import logging
from typing import Any

from app.handler.horizontal_compare import PeerThresholds, build_peer_item_conclusion, compare_peer_value
from app.handler.vibration_common import (
    AXES,
    LEVEL_ATTENTION,
    LEVEL_NORMAL,
    LEVEL_SEVERE,
    LEVEL_WARNING,
    DiagnosisItemConclusion,
    MetricDiagnosisResult,
    axis_label,
    build_metric_conclusion,
    format_value,
    is_normal_sample,
    skipped_result,
    time_feature,
)

logger = logging.getLogger(__name__)

METRIC = "vibration_intensity"
METRIC_LABEL = "振动强度"

# Fallback RMS velocity thresholds in mm/s. The user's ISO selection maps to
# a standard/category/foundation tuple; customer-specific SensorThreshold values
# override these defaults when available.
ISO_VELOCITY_LIMITS: dict[tuple[int, int, int], tuple[float, float, float]] = {
    (1, 1, 0): (0.71, 1.8, 4.5),
    (1, 1, 1): (0.71, 1.8, 4.5),
    (1, 1, 2): (0.71, 1.8, 4.5),
    (1, 2, 1): (1.12, 2.8, 7.1),
    (1, 2, 2): (1.12, 2.8, 7.1),
    (1, 3, 1): (1.8, 4.5, 11.2),
    (1, 3, 2): (2.8, 7.1, 18.0),
    (2, 1, 1): (1.8, 4.5, 11.2),
    (2, 1, 2): (2.8, 7.1, 18.0),
    (2, 2, 1): (1.8, 4.5, 11.2),
    (2, 2, 2): (2.8, 7.1, 18.0),
    (2, 3, 1): (1.8, 4.5, 11.2),
    (2, 3, 2): (2.8, 7.1, 18.0),
    (2, 4, 1): (2.8, 7.1, 18.0),
    (2, 4, 2): (2.8, 7.1, 18.0),
}
DEFAULT_VELOCITY_LIMITS = (1.8, 4.5, 11.2)
PEER_VELOCITY_THRESHOLDS = PeerThresholds(
    relative_attention=0.10,
    relative_warning=0.20,
    relative_severe=0.35,
    absolute_attention=0.5,
    absolute_warning=1.0,
    absolute_severe=2.0,
)


def run_vibration_intensity_check(
    report_id: str,
    sn: str,
    payload: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> MetricDiagnosisResult:
    result = diagnose_vibration_intensity(report_id, sn, payload, context)
    logger.info("%s", result.conclusion.conclusion)
    return result


def diagnose_vibration_intensity(
    report_id: str,
    sn: str,
    payload: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> MetricDiagnosisResult:
    if not is_normal_sample(payload):
        return skipped_result(
            metric=METRIC,
            sn=sn,
            report_id=report_id,
            reason="sample_type 不是 normal，跳过振动强度诊断",
            evidence=[f"sample_type={payload.get('sample_type')}", "rule=sample_type == normal"],
        )

    thresholds, threshold_source = _velocity_thresholds(context)
    items: list[DiagnosisItemConclusion] = []
    for axis in AXES:
        items.append(_axis_intensity_conclusion(axis, payload, context, thresholds, threshold_source))
        items.append(_axis_peer_intensity_conclusion(axis, sn, payload, context))
    conclusion = build_metric_conclusion(METRIC_LABEL, items)
    return MetricDiagnosisResult(sn=sn, report_id=report_id, metric=METRIC, conclusion=conclusion)


def _axis_intensity_conclusion(
    axis: str,
    payload: dict[str, Any],
    context: dict[str, Any] | None,
    thresholds: tuple[float, float, float],
    threshold_source: str,
) -> DiagnosisItemConclusion:
    rms_vel = time_feature(payload, axis, "rms_vel_mm_s")
    rms_acc = time_feature(payload, axis, "rms_acc_g")
    peak_acc = time_feature(payload, axis, "peak_acc_g")
    peak_to_peak = time_feature(payload, axis, "peak_to_peak_acc_g")
    label = axis_label(axis, context)
    if rms_vel is None:
        return DiagnosisItemConclusion(
            name=f"{label}振动强度",
            level="未检测",
            triggered=False,
            conclusion=f"{label}缺少 rms_vel_mm_s，无法判断振动强度",
            evidence=[f"axis={axis}", "missing_field=rms_vel_mm_s"],
        )

    attention, warning, severe = thresholds
    level = _velocity_level(rms_vel, thresholds)
    evidence = [
        f"axis={axis}",
        f"axis_label={label}",
        f"rms_vel_mm_s={format_value(rms_vel)}",
        f"attention_mm_s={format_value(attention)}",
        f"warning_mm_s={format_value(warning)}",
        f"severe_mm_s={format_value(severe)}",
        f"threshold_source={threshold_source}",
        f"rms_acc_g={format_value(rms_acc)}",
        f"peak_acc_g={format_value(peak_acc)}",
        f"peak_to_peak_acc_g={format_value(peak_to_peak)}",
    ]
    if level == LEVEL_NORMAL:
        return DiagnosisItemConclusion(
            name=f"{label}振动强度",
            level=LEVEL_NORMAL,
            triggered=False,
            conclusion=f"{label}振动速度有效值正常",
            evidence=[*evidence, "rule=rms_vel_mm_s < attention threshold"],
        )

    return DiagnosisItemConclusion(
        name=f"{label}振动强度",
        level=level,
        triggered=True,
        conclusion=f"{label}振动速度有效值达到{level}范围",
        evidence=[*evidence, "rule=rms_vel_mm_s >= level threshold"],
    )


def _axis_peer_intensity_conclusion(
    axis: str,
    sn: str,
    payload: dict[str, Any],
    context: dict[str, Any] | None,
) -> DiagnosisItemConclusion:
    label = axis_label(axis, context)
    result = compare_peer_value(
        current_sn=sn,
        current_value=time_feature(payload, axis, "rms_vel_mm_s"),
        context=context,
        field="rms_vel_mm_s",
        axis=axis,
        same_direction=True,
        thresholds=PEER_VELOCITY_THRESHOLDS,
    )
    return build_peer_item_conclusion(
        result=result,
        name=f"{label}振动强度横向比较",
        normal_text=f"{label}振动强度相对同组设备未见明显偏高",
        warning_text=f"{label}振动强度相对同组设备偏高",
        thresholds=PEER_VELOCITY_THRESHOLDS,
    )


def _velocity_thresholds(context: dict[str, Any] | None) -> tuple[tuple[float, float, float], str]:
    threshold = (((context or {}).get("thresholds") or {}).get("vibration"))
    if isinstance(threshold, dict):
        baseline = _float_or_none(threshold.get("baseline"))
        attention_delta = _float_or_none(threshold.get("rt_max_delta"))
        warning_delta = _float_or_none(threshold.get("st_max_amplitude"))
        severe_delta = _float_or_none(threshold.get("mt_max_amplitude"))
        if baseline is not None and all(v is not None for v in (attention_delta, warning_delta, severe_delta)):
            return (
                baseline + attention_delta,  # type: ignore[operator]
                baseline + warning_delta,  # type: ignore[operator]
                baseline + severe_delta,  # type: ignore[operator]
            ), "sensor_threshold"

    iso = (context or {}).get("iso")
    if isinstance(iso, dict):
        key = (
            int(iso.get("version") or 0),
            int(iso.get("category") or 0),
            int(iso.get("foundation") or 0),
        )
        if key in ISO_VELOCITY_LIMITS:
            return ISO_VELOCITY_LIMITS[key], f"iso:{key}"
    return DEFAULT_VELOCITY_LIMITS, "default_iso_fallback"


def _velocity_level(value: float, thresholds: tuple[float, float, float]) -> str:
    attention, warning, severe = thresholds
    if value >= severe:
        return LEVEL_SEVERE
    if value >= warning:
        return LEVEL_WARNING
    if value >= attention:
        return LEVEL_ATTENTION
    return LEVEL_NORMAL


def _float_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None
