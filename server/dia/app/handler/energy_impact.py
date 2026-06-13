"""
Energy impact diagnosis.

This module detects impact-like vibration behavior: high crest factor, high
kurtosis, peak-to-peak jumps, and high-frequency energy concentration.
"""

import logging
from typing import Any

from app.handler.vibration_common import (
    AXES,
    HISTORY_WINDOW_SIZE,
    LEVEL_ATTENTION,
    LEVEL_NORMAL,
    LEVEL_NOT_CHECKED,
    LEVEL_SEVERE,
    LEVEL_WARNING,
    AxisFeaturePoint,
    DiagnosisItemConclusion,
    MetricDiagnosisResult,
    axis_label,
    band_feature,
    build_metric_conclusion,
    format_value,
    is_normal_sample,
    level_from_ratio,
    load_recent_axis_feature_points,
    mean,
    relative_delta,
    skipped_result,
    time_feature,
)

logger = logging.getLogger(__name__)

METRIC = "energy_impact"
METRIC_LABEL = "能量冲击"
HISTORY_FIELDS = ["crest_factor", "kurtosis", "peak_to_peak_acc_g", "band_2000_5000"]

CREST_ATTENTION = 4.0
CREST_WARNING = 6.0
CREST_SEVERE = 8.0
KURTOSIS_ATTENTION = 4.0
KURTOSIS_WARNING = 6.0
KURTOSIS_SEVERE = 8.0
REL_ATTENTION = 0.5
REL_WARNING = 1.0
REL_SEVERE = 2.0
MIN_HISTORY_POINTS = 6


def run_energy_impact_check(
    report_id: str,
    sn: str,
    payload: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> MetricDiagnosisResult:
    result = diagnose_energy_impact(report_id, sn, payload, context)
    logger.info("%s", result.conclusion.conclusion)
    return result


def diagnose_energy_impact(
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
            reason="sample_type 不是 normal，跳过能量冲击诊断",
            evidence=[f"sample_type={payload.get('sample_type')}", "rule=sample_type == normal"],
        )

    history = load_recent_axis_feature_points(sn, HISTORY_FIELDS, HISTORY_WINDOW_SIZE)
    items: list[DiagnosisItemConclusion] = []
    for axis in AXES:
        axis_history = [
            point for point in history if point.axis == axis and point.report_id != report_id
        ][-HISTORY_WINDOW_SIZE:]
        items.extend(
            [
                _crest_factor_conclusion(axis, payload, context),
                _kurtosis_conclusion(axis, payload, context),
                _relative_feature_conclusion(
                    axis=axis,
                    payload=payload,
                    context=context,
                    history=axis_history,
                    current_value=time_feature(payload, axis, "peak_to_peak_acc_g"),
                    history_field="peak_to_peak_acc_g",
                    name="峰峰值冲击",
                    normal_text="峰峰值未见突增",
                    warning_text="峰峰值相比历史基线突增",
                ),
                _relative_feature_conclusion(
                    axis=axis,
                    payload=payload,
                    context=context,
                    history=axis_history,
                    current_value=band_feature(payload, axis, "2000_5000"),
                    history_field="band_2000_5000",
                    name="高频能量冲击",
                    normal_text="高频能量占比未见突增",
                    warning_text="高频能量占比相比历史基线突增",
                ),
            ]
        )

    conclusion = build_metric_conclusion(METRIC_LABEL, items)
    return MetricDiagnosisResult(sn=sn, report_id=report_id, metric=METRIC, conclusion=conclusion)


def _crest_factor_conclusion(
    axis: str,
    payload: dict[str, Any],
    context: dict[str, Any] | None,
) -> DiagnosisItemConclusion:
    return _absolute_feature_conclusion(
        axis=axis,
        context=context,
        value=time_feature(payload, axis, "crest_factor"),
        name="冲击因子",
        field_name="crest_factor",
        attention=CREST_ATTENTION,
        warning=CREST_WARNING,
        severe=CREST_SEVERE,
        normal_text="冲击因子正常",
        warning_text="冲击因子偏高",
    )


def _kurtosis_conclusion(
    axis: str,
    payload: dict[str, Any],
    context: dict[str, Any] | None,
) -> DiagnosisItemConclusion:
    return _absolute_feature_conclusion(
        axis=axis,
        context=context,
        value=time_feature(payload, axis, "kurtosis"),
        name="峭度",
        field_name="kurtosis",
        attention=KURTOSIS_ATTENTION,
        warning=KURTOSIS_WARNING,
        severe=KURTOSIS_SEVERE,
        normal_text="峭度正常",
        warning_text="峭度偏高",
    )


def _absolute_feature_conclusion(
    *,
    axis: str,
    context: dict[str, Any] | None,
    value: float | None,
    name: str,
    field_name: str,
    attention: float,
    warning: float,
    severe: float,
    normal_text: str,
    warning_text: str,
) -> DiagnosisItemConclusion:
    label = axis_label(axis, context)
    if value is None:
        return DiagnosisItemConclusion(
            name=f"{label}{name}",
            level=LEVEL_NOT_CHECKED,
            triggered=False,
            conclusion=f"{label}缺少 {field_name}，无法判断{name}",
            evidence=[f"axis={axis}", f"missing_field={field_name}"],
        )

    level = _absolute_level(value, attention, warning, severe)
    evidence = [
        f"axis={axis}",
        f"axis_label={label}",
        f"{field_name}={format_value(value)}",
        f"attention={format_value(attention)}",
        f"warning={format_value(warning)}",
        f"severe={format_value(severe)}",
    ]
    if level == LEVEL_NORMAL:
        return DiagnosisItemConclusion(
            name=f"{label}{name}",
            level=LEVEL_NORMAL,
            triggered=False,
            conclusion=f"{label}{normal_text}",
            evidence=[*evidence, f"rule={field_name} < attention threshold"],
        )
    return DiagnosisItemConclusion(
        name=f"{label}{name}",
        level=level,
        triggered=True,
        conclusion=f"{label}{warning_text}，达到{level}范围",
        evidence=[*evidence, f"rule={field_name} >= level threshold"],
    )


def _relative_feature_conclusion(
    *,
    axis: str,
    payload: dict[str, Any],
    context: dict[str, Any] | None,
    history: list[AxisFeaturePoint],
    current_value: float | None,
    history_field: str,
    name: str,
    normal_text: str,
    warning_text: str,
) -> DiagnosisItemConclusion:
    del payload
    label = axis_label(axis, context)
    if current_value is None:
        return DiagnosisItemConclusion(
            name=f"{label}{name}",
            level=LEVEL_NOT_CHECKED,
            triggered=False,
            conclusion=f"{label}缺少当前值，无法判断{name}",
            evidence=[f"axis={axis}", f"missing_field={history_field}"],
        )

    history_values = [point.fields[history_field] for point in history if history_field in point.fields]
    baseline = mean(history_values[-HISTORY_WINDOW_SIZE:])
    if len(history_values) < MIN_HISTORY_POINTS or baseline is None:
        return DiagnosisItemConclusion(
            name=f"{label}{name}",
            level=LEVEL_NOT_CHECKED,
            triggered=False,
            conclusion=f"{label}历史样本不足，无法判断{name}",
            evidence=[
                f"axis={axis}",
                f"{history_field}={format_value(current_value)}",
                f"history_count={len(history_values)}",
                f"need_history_count={MIN_HISTORY_POINTS}",
            ],
        )

    ratio = relative_delta(current_value, baseline)
    level = level_from_ratio(ratio, REL_ATTENTION, REL_WARNING, REL_SEVERE)
    evidence = [
        f"axis={axis}",
        f"axis_label={label}",
        f"{history_field}={format_value(current_value)}",
        f"baseline={format_value(baseline)}",
        f"relative_delta={format_value(ratio)}",
        f"history_count={len(history_values)}",
        f"attention_delta={REL_ATTENTION}",
        f"warning_delta={REL_WARNING}",
        f"severe_delta={REL_SEVERE}",
    ]
    if level is None:
        return DiagnosisItemConclusion(
            name=f"{label}{name}",
            level=LEVEL_NORMAL,
            triggered=False,
            conclusion=f"{label}{normal_text}",
            evidence=[*evidence, "rule=relative_delta < attention threshold"],
        )
    return DiagnosisItemConclusion(
        name=f"{label}{name}",
        level=level,
        triggered=True,
        conclusion=f"{label}{warning_text}，达到{level}范围",
        evidence=[*evidence, "rule=relative_delta >= level threshold"],
    )


def _absolute_level(value: float, attention: float, warning: float, severe: float) -> str:
    if value >= severe:
        return LEVEL_SEVERE
    if value >= warning:
        return LEVEL_WARNING
    if value >= attention:
        return LEVEL_ATTENTION
    return LEVEL_NORMAL
