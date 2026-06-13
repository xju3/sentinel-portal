"""
Main frequency and peak-structure diagnosis.

This module detects changes in frequency-domain structure rather than assigning
specific mechanical fault names. It compares the current dominant peak,
spectral centroid, and spectral entropy against recent normal history.
"""

import logging
from typing import Any

from app.handler.vibration_common import (
    AXES,
    HISTORY_WINDOW_SIZE,
    LEVEL_NORMAL,
    LEVEL_NOT_CHECKED,
    AxisFeaturePoint,
    DiagnosisItemConclusion,
    MetricDiagnosisResult,
    axis_label,
    build_metric_conclusion,
    format_value,
    freq_feature,
    is_normal_sample,
    level_from_ratio,
    load_recent_axis_feature_points,
    mean,
    peak_features,
    relative_delta,
    skipped_result,
)

logger = logging.getLogger(__name__)

METRIC = "peak_structure"
METRIC_LABEL = "主频/峰值结构"
HISTORY_FIELDS = [
    "spectral_centroid_hz",
    "spectral_entropy",
    "peak1_freq_hz",
    "peak1_amp_g",
]

MIN_HISTORY_POINTS = 6
FREQ_REL_ATTENTION = 0.10
FREQ_REL_WARNING = 0.20
FREQ_REL_SEVERE = 0.35
AMP_REL_ATTENTION = 0.50
AMP_REL_WARNING = 1.00
AMP_REL_SEVERE = 2.00
CENTROID_REL_ATTENTION = 0.10
CENTROID_REL_WARNING = 0.20
CENTROID_REL_SEVERE = 0.35
ENTROPY_DELTA_ATTENTION = 0.05
ENTROPY_DELTA_WARNING = 0.10
ENTROPY_DELTA_SEVERE = 0.20


def run_peak_structure_check(
    report_id: str,
    sn: str,
    payload: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> MetricDiagnosisResult:
    result = diagnose_peak_structure(report_id, sn, payload, context)
    logger.info("%s", result.conclusion.conclusion)
    return result


def diagnose_peak_structure(
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
            reason="sample_type 不是 normal，跳过主频/峰值结构诊断",
            evidence=[f"sample_type={payload.get('sample_type')}", "rule=sample_type == normal"],
        )

    history = load_recent_axis_feature_points(sn, HISTORY_FIELDS, HISTORY_WINDOW_SIZE)
    items: list[DiagnosisItemConclusion] = []
    for axis in AXES:
        current_peak = _dominant_peak(payload, axis)
        axis_history = [
            point for point in history if point.axis == axis and point.report_id != report_id
        ][-HISTORY_WINDOW_SIZE:]
        items.extend(
            [
                _relative_structure_conclusion(
                    axis=axis,
                    context=context,
                    history=axis_history,
                    current_value=current_peak.get("freq_hz") if current_peak else None,
                    history_field="peak1_freq_hz",
                    name="主峰频率漂移",
                    normal_text="主峰频率未见明显漂移",
                    warning_text="主峰频率相对历史基线漂移",
                    attention=FREQ_REL_ATTENTION,
                    warning=FREQ_REL_WARNING,
                    severe=FREQ_REL_SEVERE,
                    absolute=True,
                ),
                _relative_structure_conclusion(
                    axis=axis,
                    context=context,
                    history=axis_history,
                    current_value=current_peak.get("amp_g") if current_peak else None,
                    history_field="peak1_amp_g",
                    name="主峰幅值变化",
                    normal_text="主峰幅值未见明显突增",
                    warning_text="主峰幅值相对历史基线突增",
                    attention=AMP_REL_ATTENTION,
                    warning=AMP_REL_WARNING,
                    severe=AMP_REL_SEVERE,
                    absolute=False,
                ),
                _relative_structure_conclusion(
                    axis=axis,
                    context=context,
                    history=axis_history,
                    current_value=freq_feature(payload, axis, "spectral_centroid_hz"),
                    history_field="spectral_centroid_hz",
                    name="频谱质心漂移",
                    normal_text="频谱质心未见明显漂移",
                    warning_text="频谱质心相对历史基线漂移",
                    attention=CENTROID_REL_ATTENTION,
                    warning=CENTROID_REL_WARNING,
                    severe=CENTROID_REL_SEVERE,
                    absolute=True,
                ),
                _entropy_conclusion(axis, payload, context, axis_history),
            ]
        )

    conclusion = build_metric_conclusion(METRIC_LABEL, items)
    return MetricDiagnosisResult(sn=sn, report_id=report_id, metric=METRIC, conclusion=conclusion)


def _dominant_peak(payload: dict[str, Any], axis: str) -> dict[str, float] | None:
    peaks = peak_features(payload, axis)
    if not peaks:
        return None
    return max(peaks, key=lambda peak: peak["amp_g"])


def _relative_structure_conclusion(
    *,
    axis: str,
    context: dict[str, Any] | None,
    history: list[AxisFeaturePoint],
    current_value: float | None,
    history_field: str,
    name: str,
    normal_text: str,
    warning_text: str,
    attention: float,
    warning: float,
    severe: float,
    absolute: bool,
) -> DiagnosisItemConclusion:
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
    ratio_for_level = abs(ratio) if absolute and ratio is not None else ratio
    level = level_from_ratio(ratio_for_level, attention, warning, severe)
    evidence = [
        f"axis={axis}",
        f"axis_label={label}",
        f"{history_field}={format_value(current_value)}",
        f"baseline={format_value(baseline)}",
        f"relative_delta={format_value(ratio)}",
        f"history_count={len(history_values)}",
        f"attention_delta={attention}",
        f"warning_delta={warning}",
        f"severe_delta={severe}",
    ]
    if level is None:
        return DiagnosisItemConclusion(
            name=f"{label}{name}",
            level=LEVEL_NORMAL,
            triggered=False,
            conclusion=f"{label}{normal_text}",
            evidence=[*evidence, "rule=relative_delta below attention threshold"],
        )
    return DiagnosisItemConclusion(
        name=f"{label}{name}",
        level=level,
        triggered=True,
        conclusion=f"{label}{warning_text}，达到{level}范围",
        evidence=[*evidence, "rule=relative_delta >= level threshold"],
    )


def _entropy_conclusion(
    axis: str,
    payload: dict[str, Any],
    context: dict[str, Any] | None,
    history: list[AxisFeaturePoint],
) -> DiagnosisItemConclusion:
    label = axis_label(axis, context)
    current = freq_feature(payload, axis, "spectral_entropy")
    if current is None:
        return DiagnosisItemConclusion(
            name=f"{label}频谱熵变化",
            level=LEVEL_NOT_CHECKED,
            triggered=False,
            conclusion=f"{label}缺少 spectral_entropy，无法判断频谱熵变化",
            evidence=[f"axis={axis}", "missing_field=spectral_entropy"],
        )

    history_values = [point.fields["spectral_entropy"] for point in history if "spectral_entropy" in point.fields]
    baseline = mean(history_values[-HISTORY_WINDOW_SIZE:])
    if len(history_values) < MIN_HISTORY_POINTS or baseline is None:
        return DiagnosisItemConclusion(
            name=f"{label}频谱熵变化",
            level=LEVEL_NOT_CHECKED,
            triggered=False,
            conclusion=f"{label}历史样本不足，无法判断频谱熵变化",
            evidence=[
                f"axis={axis}",
                f"spectral_entropy={format_value(current)}",
                f"history_count={len(history_values)}",
                f"need_history_count={MIN_HISTORY_POINTS}",
            ],
        )

    delta = current - baseline
    abs_delta = abs(delta)
    level = _entropy_level(abs_delta)
    evidence = [
        f"axis={axis}",
        f"axis_label={label}",
        f"spectral_entropy={format_value(current)}",
        f"baseline={format_value(baseline)}",
        f"delta={format_value(delta)}",
        f"history_count={len(history_values)}",
        f"attention_delta={ENTROPY_DELTA_ATTENTION}",
        f"warning_delta={ENTROPY_DELTA_WARNING}",
        f"severe_delta={ENTROPY_DELTA_SEVERE}",
    ]
    if level is None:
        return DiagnosisItemConclusion(
            name=f"{label}频谱熵变化",
            level=LEVEL_NORMAL,
            triggered=False,
            conclusion=f"{label}频谱熵未见明显变化",
            evidence=[*evidence, "rule=abs(delta) < attention threshold"],
        )
    direction_text = "升高" if delta > 0 else "降低"
    return DiagnosisItemConclusion(
        name=f"{label}频谱熵变化",
        level=level,
        triggered=True,
        conclusion=f"{label}频谱熵明显{direction_text}，达到{level}范围",
        evidence=[*evidence, "rule=abs(delta) >= level threshold"],
    )


def _entropy_level(delta: float) -> str | None:
    if delta >= ENTROPY_DELTA_SEVERE:
        return "严重"
    if delta >= ENTROPY_DELTA_WARNING:
        return "警告"
    if delta >= ENTROPY_DELTA_ATTENTION:
        return "关注"
    return None
