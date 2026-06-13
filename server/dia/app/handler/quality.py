"""
Data quality diagnosis.

This module checks whether a result.json payload is usable before metric-level
diagnosis runs. It focuses on acquisition quality: quality status, accepted
attempts, required axis quality fields, clipping, and range consistency.
"""

import logging
from dataclasses import dataclass
from numbers import Real
from typing import Any

logger = logging.getLogger(__name__)

AXES = ("X", "Y", "Z")
CLIP_RATIO_SEVERE = 0.01
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
class QualityCheckConclusion:
    name: str
    level: str
    triggered: bool
    conclusion: str
    evidence: list[str]


@dataclass(frozen=True)
class QualityConclusion:
    level: str
    triggered: bool
    conclusion: str
    evidence: list[str]
    items: list[QualityCheckConclusion]


@dataclass(frozen=True)
class QualityDiagnosisResult:
    sn: str
    report_id: str
    metric: str
    usable: bool
    conclusion: QualityConclusion


def run_quality_check(report_id: str, sn: str, payload: dict[str, Any]) -> QualityDiagnosisResult:
    """Run data quality diagnosis for the full result.json payload."""
    result = diagnose_quality(report_id=report_id, sn=sn, payload=payload)
    logger.info("%s", _format_quality_conclusion_log(result))
    return result


def diagnose_quality(report_id: str, sn: str, payload: dict[str, Any]) -> QualityDiagnosisResult:
    """Check whether the payload quality section permits downstream diagnosis."""
    quality = payload.get("quality")
    if not isinstance(quality, dict):
        item = QualityCheckConclusion(
            name="质量字段",
            level=LEVEL_SEVERE,
            triggered=True,
            conclusion="缺少 quality 对象，数据不可用于后续诊断",
            evidence=["quality_type=missing_or_invalid", "rule=quality must be an object"],
        )
        conclusion = _build_quality_conclusion([item])
        return QualityDiagnosisResult(
            sn=sn,
            report_id=report_id,
            metric="quality",
            usable=False,
            conclusion=conclusion,
        )

    accepted_attempt = _select_accepted_attempt(quality)
    items = [
        _quality_status_conclusion(quality),
        _accepted_attempt_conclusion(quality, accepted_attempt),
        _axis_quality_conclusion(accepted_attempt),
        _range_conclusion(payload, quality, accepted_attempt),
    ]
    conclusion = _build_quality_conclusion(items)
    return QualityDiagnosisResult(
        sn=sn,
        report_id=report_id,
        metric="quality",
        usable=conclusion.level != LEVEL_SEVERE,
        conclusion=conclusion,
    )


def _quality_status_conclusion(quality: dict[str, Any]) -> QualityCheckConclusion:
    status = quality.get("status")
    if status != "ok":
        return QualityCheckConclusion(
            name="质量状态",
            level=LEVEL_SEVERE,
            triggered=True,
            conclusion="采样质量状态不是 ok，数据不可用于后续诊断",
            evidence=[f"quality.status={status}", "rule=quality.status == ok"],
        )
    return QualityCheckConclusion(
        name="质量状态",
        level=LEVEL_NORMAL,
        triggered=False,
        conclusion="采样质量状态正常",
        evidence=["quality.status=ok", "rule=quality.status == ok"],
    )


def _accepted_attempt_conclusion(
    quality: dict[str, Any],
    accepted_attempt: dict[str, Any] | None,
) -> QualityCheckConclusion:
    attempts = quality.get("attempts")
    attempt_count = len(attempts) if isinstance(attempts, list) else 0
    if accepted_attempt is None:
        return QualityCheckConclusion(
            name="有效采样",
            level=LEVEL_SEVERE,
            triggered=True,
            conclusion="没有 accepted=true 的采样尝试，数据不可用于后续诊断",
            evidence=[
                f"attempt_count={attempt_count}",
                "accepted_attempt=false",
                "rule=at least one quality.attempts item accepted",
            ],
        )
    return QualityCheckConclusion(
        name="有效采样",
        level=LEVEL_NORMAL,
        triggered=False,
        conclusion="存在 accepted=true 的采样尝试",
        evidence=[
            f"attempt_count={attempt_count}",
            f"accepted_reason={accepted_attempt.get('reason')}",
            f"accepted_range_g={_format_value(accepted_attempt.get('range_g'))}",
        ],
    )


def _axis_quality_conclusion(accepted_attempt: dict[str, Any] | None) -> QualityCheckConclusion:
    if accepted_attempt is None:
        return QualityCheckConclusion(
            name="轴质量",
            level=LEVEL_SEVERE,
            triggered=True,
            conclusion="没有有效采样尝试，无法检查轴质量",
            evidence=["accepted_attempt=false"],
        )

    axes = accepted_attempt.get("axes")
    if not isinstance(axes, dict):
        return QualityCheckConclusion(
            name="轴质量",
            level=LEVEL_SEVERE,
            triggered=True,
            conclusion="有效采样缺少 axes 对象，数据不可用于后续诊断",
            evidence=["axes_type=missing_or_invalid", "rule=accepted_attempt.axes must be an object"],
        )

    evidence: list[str] = []
    max_clip_ratio = 0.0
    total_clip_count = 0
    missing_axes: list[str] = []
    invalid_axes: list[str] = []
    for axis in AXES:
        axis_payload = axes.get(axis)
        if not isinstance(axis_payload, dict):
            missing_axes.append(axis)
            continue

        max_abs_g = axis_payload.get("max_abs_g")
        clip_count = axis_payload.get("clip_count")
        clip_ratio = axis_payload.get("clip_ratio")
        if not _is_number(max_abs_g) or not _is_non_bool_int(clip_count) or not _is_number(clip_ratio):
            invalid_axes.append(axis)
            continue

        max_clip_ratio = max(max_clip_ratio, float(clip_ratio))
        total_clip_count += int(clip_count)
        evidence.append(
            f"{axis}: max_abs_g={_format_value(max_abs_g)}, "
            f"clip_count={clip_count}, clip_ratio={_format_value(clip_ratio)}"
        )

    if missing_axes or invalid_axes:
        return QualityCheckConclusion(
            name="轴质量",
            level=LEVEL_SEVERE,
            triggered=True,
            conclusion="有效采样的轴质量字段不完整，数据不可用于后续诊断",
            evidence=[
                *evidence,
                f"missing_axes={','.join(missing_axes) or '-'}",
                f"invalid_axes={','.join(invalid_axes) or '-'}",
                "rule=X/Y/Z max_abs_g, clip_count, clip_ratio are required",
            ],
        )

    if max_clip_ratio >= CLIP_RATIO_SEVERE:
        return QualityCheckConclusion(
            name="轴质量",
            level=LEVEL_SEVERE,
            triggered=True,
            conclusion="采样出现明显削顶，数据不可用于后续诊断",
            evidence=[
                *evidence,
                f"max_clip_ratio={_format_value(max_clip_ratio)}",
                f"severe_clip_ratio={_format_value(CLIP_RATIO_SEVERE)}",
                "rule=max_clip_ratio >= severe_clip_ratio",
            ],
        )

    if total_clip_count > 0:
        return QualityCheckConclusion(
            name="轴质量",
            level=LEVEL_WARNING,
            triggered=True,
            conclusion="采样存在少量削顶，后续诊断结果需谨慎解释",
            evidence=[
                *evidence,
                f"total_clip_count={total_clip_count}",
                "rule=total_clip_count > 0",
            ],
        )

    return QualityCheckConclusion(
        name="轴质量",
        level=LEVEL_NORMAL,
        triggered=False,
        conclusion="三轴采样未发现削顶",
        evidence=[*evidence, "rule=all clip_count == 0 and clip_ratio < severe threshold"],
    )


def _range_conclusion(
    payload: dict[str, Any],
    quality: dict[str, Any],
    accepted_attempt: dict[str, Any] | None,
) -> QualityCheckConclusion:
    auto_range = quality.get("auto_range")
    requested_range_g = payload.get("requested_range_g")
    range_g = payload.get("range_g")
    accepted_range_g = accepted_attempt.get("range_g") if accepted_attempt else None
    evidence = [
        f"auto_range={auto_range}",
        f"requested_range_g={_format_value(requested_range_g)}",
        f"range_g={_format_value(range_g)}",
        f"accepted_range_g={_format_value(accepted_range_g)}",
    ]

    if not _is_number(range_g):
        return QualityCheckConclusion(
            name="量程一致性",
            level=LEVEL_SEVERE,
            triggered=True,
            conclusion="缺少有效 range_g，数据不可用于后续诊断",
            evidence=[*evidence, "rule=range_g must be numeric"],
        )

    if accepted_range_g is not None and _is_number(accepted_range_g) and float(accepted_range_g) != float(range_g):
        return QualityCheckConclusion(
            name="量程一致性",
            level=LEVEL_WARNING,
            triggered=True,
            conclusion="最终量程与有效采样量程不一致，后续诊断需谨慎解释",
            evidence=[*evidence, "rule=range_g == accepted_attempt.range_g"],
        )

    if auto_range is True:
        return QualityCheckConclusion(
            name="量程一致性",
            level=LEVEL_ATTENTION,
            triggered=True,
            conclusion="本次采样发生自动量程调整，后续趋势对比需注意量程变化",
            evidence=[*evidence, "rule=auto_range is true"],
        )

    return QualityCheckConclusion(
        name="量程一致性",
        level=LEVEL_NORMAL,
        triggered=False,
        conclusion="量程信息一致",
        evidence=[*evidence, "rule=range information is consistent"],
    )


def _build_quality_conclusion(items: list[QualityCheckConclusion]) -> QualityConclusion:
    level = _highest_level(items)
    triggered_items = [item for item in items if item.triggered]
    evidence = [
        f"{item.name}: level={item.level}, triggered={item.triggered}, {item.conclusion}"
        for item in items
    ]
    if not triggered_items:
        return QualityConclusion(
            level=LEVEL_NORMAL,
            triggered=False,
            conclusion="数据质量诊断结论：正常，数据可用于后续诊断",
            evidence=evidence,
            items=items,
        )

    reasons = "；".join(item.conclusion for item in triggered_items)
    suffix = "数据不可用于后续诊断" if level == LEVEL_SEVERE else "数据可用于后续诊断，但需关注质量提示"
    return QualityConclusion(
        level=level,
        triggered=True,
        conclusion=f"数据质量诊断结论：{level}，{reasons}；{suffix}",
        evidence=evidence,
        items=items,
    )


def _highest_level(items: list[QualityCheckConclusion]) -> str:
    return max(items, key=lambda item: CONCLUSION_LEVEL_ORDER.get(item.level, 0)).level


def _select_accepted_attempt(quality: dict[str, Any]) -> dict[str, Any] | None:
    attempts = quality.get("attempts")
    if not isinstance(attempts, list):
        return None
    for attempt in reversed(attempts):
        if isinstance(attempt, dict) and attempt.get("accepted") is True:
            return attempt
    return None


def _format_quality_conclusion_log(result: QualityDiagnosisResult) -> str:
    lines = [
        "Quality diagnosis conclusion",
        f"  sn: {result.sn}",
        f"  report_id: {result.report_id}",
        f"  usable: {result.usable}",
        f"  level: {result.conclusion.level}",
        f"  triggered: {result.conclusion.triggered}",
        f"  conclusion: {result.conclusion.conclusion}",
        "  checks:",
    ]
    for item in result.conclusion.items:
        lines.extend(
            [
                f"    - {item.name}",
                f"      level: {item.level}",
                f"      triggered: {item.triggered}",
                f"      conclusion: {item.conclusion}",
                "      evidence:",
            ]
        )
        lines.extend(f"        - {evidence}" for evidence in item.evidence)
    return "\n".join(lines)


def _is_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, Real)


def _is_non_bool_int(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, int)


def _format_value(value: Any) -> str:
    if isinstance(value, float):
        return format(value, ".15g")
    return str(value)
