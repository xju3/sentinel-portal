"""
Temperature diagnosis.

This module runs only the temperature part of a diagnosis job. The current
report's `sn` and `temperature_c` come from the downloaded result JSON, not
from InfluxDB, because diagnosis starts immediately after Telegraf accepts the
write and the current report may not be query-visible yet.

Recent temperature history is read from Redis first using the structure
`{"temp_c": 20.0, "ts_ms": 170000}`. If Redis has fewer than 72 points, the
module falls back to InfluxDB, backfills Redis with the recent window, and then
continues diagnosis. The current JSON point is pushed to Redis after history is
loaded so the next diagnosis can avoid the InfluxDB query.

Temperature is checked on four tracks:
1. Absolute temperature:
   If the current report temperature reaches 50°C or above, log a warning
   regardless of short-window, long-window, or single-period rise behavior.
2. Short-window rise:
   Prefer the latest 30 minutes of reports, falling back to the latest 6 reports
   when timestamps are not usable. A 0.5°C delta is treated as the single-period
   noise band: small increases can still accumulate into a warning, small drops
   do not break the window, and a drop of 0.5°C or more ends the short-window
   rise chain. The window logs "持续升温" while the latest point is still
   rising, "高位保持" when a prior rise is held near the elevated temperature,
   and "回落结束" when the rise chain has clearly dropped.
3. Trend rise:
   Read recent unique report temperatures for the same sensor and inject the
   current report temperature if it is not visible in InfluxDB yet. Use the
   latest 72 reports as a sliding window; compare the newest point against the
   previous 71 points with Z-Score / 3-Sigma and compare the latter half of the
   window against the former half to catch chronic upward drift.
4. Short-term rise:
   Compare the current report temperature with the previous report for the
   same sensor. If the rise is greater than 10%, log "关注"; greater than 15%,
   log "警告"; greater than 20%, log "严重".

Every diagnosis returns a top-level conclusion and one conclusion for each
track. The top-level conclusion uses the highest level reported by the four
tracks; skipped tracks are marked as "未检测" and do not raise the overall
level.

InfluxDB stores `temperature_c` once per axis row under the same report_id, so
historical reads deduplicate by report_id before any diagnosis calculation.

redis_key: dia:temperature:{sn}:recent
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from math import sqrt
from typing import Any

from app.handler.horizontal_compare import PeerComparisonResult, PeerThresholds, compare_peer_value
from app.handler.temperature_cache import (
    TEMPERATURE_CACHE_LIMIT,
    TemperatureCachePoint,
    get_recent_temperature_points,
    push_recent_temperature_point,
    replace_recent_temperature_points,
)

logger = logging.getLogger(__name__)

MEASUREMENT = "vibration_feature"
TEMPERATURE_FIELD = "temperature_c"
TREND_WINDOW_SIZE = 72
RECENT_QUERY_LIMIT = TREND_WINDOW_SIZE + 1
SHORT_TERM_ATTENTION_RATIO = 0.10
SHORT_TERM_WARNING_RATIO = 0.15
SHORT_TERM_SEVERE_RATIO = 0.20
SHORT_WINDOW_SIZE = 6
SHORT_WINDOW_MIN_POINTS = 3
SHORT_WINDOW_DURATION_MS = 30 * 60 * 1000
TEMP_STABLE_DELTA_C = 0.5
SHORT_WINDOW_ATTENTION_DELTA_C = 1.0
SHORT_WINDOW_WARNING_DELTA_C = 2.0
SHORT_WINDOW_SEVERE_DELTA_C = 3.0
ABSOLUTE_TEMPERATURE_WARNING_C = 50.0
TREND_SIGMA_LIMIT = 3.0
TREND_DRIFT_ATTENTION_DELTA_C = 1.5
TREND_DRIFT_WARNING_DELTA_C = 3.0
TREND_DRIFT_SEVERE_DELTA_C = 5.0
PEER_TEMPERATURE_THRESHOLDS = PeerThresholds(
    relative_attention=0.05,
    relative_warning=0.10,
    relative_severe=0.15,
    absolute_attention=2.0,
    absolute_warning=3.0,
    absolute_severe=5.0,
)
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
class ReportTemperature:
    report_id: str
    temperature_c: float
    sort_key: Any


@dataclass(frozen=True)
class ShortTermTemperatureResult:
    enough_data: bool
    current_temperature_c: float | None
    previous_temperature_c: float | None
    increase_ratio: float | None
    level: str | None


@dataclass(frozen=True)
class TrendTemperatureResult:
    enough_data: bool
    report_count: int
    status: str | None
    level: str | None
    current_temperature_c: float | None
    mean_temperature_c: float | None
    sigma_temperature_c: float | None
    z_score: float | None
    baseline_mean_temperature_c: float | None
    recent_mean_temperature_c: float | None
    drift_delta_c: float | None
    warning: bool


@dataclass(frozen=True)
class ShortWindowTemperatureResult:
    enough_data: bool
    status: str | None
    level: str | None
    window_count: int
    window_duration_ms: int | None
    start_temperature_c: float | None
    current_temperature_c: float | None
    cumulative_delta_c: float | None
    latest_delta_c: float | None


@dataclass(frozen=True)
class AbsoluteTemperatureResult:
    enough_data: bool
    current_temperature_c: float | None
    threshold_c: float
    level: str | None


@dataclass(frozen=True)
class TemperatureCheckConclusion:
    name: str
    level: str
    triggered: bool
    conclusion: str
    evidence: list[str]


@dataclass(frozen=True)
class TemperatureConclusion:
    level: str
    triggered: bool
    conclusion: str
    evidence: list[str]
    items: list[TemperatureCheckConclusion]


@dataclass(frozen=True)
class TemperatureDiagnosisResult:
    sn: str
    report_id: str
    report_count: int
    absolute: AbsoluteTemperatureResult
    short_term: ShortTermTemperatureResult
    short_window: ShortWindowTemperatureResult
    trend: TrendTemperatureResult
    peer: PeerComparisonResult
    conclusion: TemperatureConclusion


def run_temperature_check(
    report_id: str,
    sn: str,
    current_temperature_c: float,
    current_ts_ms: int,
    context: dict[str, Any] | None = None,
) -> TemperatureDiagnosisResult:
    """Run temperature diagnosis for the sensor that produced report_id."""
    # logger.info(
    #     "Temperature diagnosis started: report_id=%s sn=%s current_temperature_c=%s",
    #     report_id,
    #     sn,
    #     current_temperature_c,
    # )
    reports = load_recent_report_temperatures(sn, limit=RECENT_QUERY_LIMIT)
    # logger.info(
    #     "Temperature history loaded: report_id=%s sn=%s history_report_count=%s",
    #     report_id,
    #     sn,
    # len(reports),
    # )
    reports = _ensure_current_report_temperature(
        reports,
        report_id,
        current_temperature_c,
        current_ts_ms,
    )
    push_recent_temperature_point(
        sn,
        TemperatureCachePoint(temp_c=current_temperature_c, ts_ms=current_ts_ms),
        limit=TEMPERATURE_CACHE_LIMIT,
    )
    result = diagnose_temperature(sn, report_id, reports, context)
    _log_temperature_result(result)
    # logger.info(
    #     "Temperature diagnosis finished: report_id=%s sn=%s report_count=%s",
    #     report_id,
    #     sn,
    #     result.report_count,
    # )
    return result


def diagnose_temperature(
    sn: str,
    report_id: str,
    reports: list[ReportTemperature],
    context: dict[str, Any] | None = None,
) -> TemperatureDiagnosisResult:
    """Run short-term and trend temperature checks from unique report temperatures."""
    unique_reports = _dedupe_report_temperatures(reports)
    current_index = _find_report_index(unique_reports, report_id)
    current_index = current_index if current_index is not None else len(unique_reports) - 1
    current = unique_reports[current_index] if current_index >= 0 else None
    previous = unique_reports[current_index - 1] if current_index > 0 else None

    history_to_current = unique_reports[: current_index + 1]
    absolute = check_absolute_temperature(current)
    short_term = check_short_term_temperature_rise(current, previous)
    short_window = check_short_window_temperature_rise(history_to_current)
    trend = check_temperature_trend(history_to_current)
    peer = check_peer_temperature(sn, current, context)
    conclusion = build_temperature_conclusion(
        absolute=absolute,
        short_window=short_window,
        trend=trend,
        short_term=short_term,
        peer=peer,
    )
    return TemperatureDiagnosisResult(
        sn=sn,
        report_id=report_id,
        report_count=len(unique_reports),
        absolute=absolute,
        short_term=short_term,
        short_window=short_window,
        trend=trend,
        peer=peer,
        conclusion=conclusion,
    )


def check_peer_temperature(
    sn: str,
    current: ReportTemperature | None,
    context: dict[str, Any] | None,
) -> PeerComparisonResult:
    return compare_peer_value(
        current_sn=sn,
        current_value=current.temperature_c if current else None,
        context=context,
        field=TEMPERATURE_FIELD,
        thresholds=PEER_TEMPERATURE_THRESHOLDS,
    )


def check_absolute_temperature(current: ReportTemperature | None) -> AbsoluteTemperatureResult:
    """Alarm when the current temperature reaches the absolute limit."""
    if current is None:
        return AbsoluteTemperatureResult(
            enough_data=False,
            current_temperature_c=None,
            threshold_c=ABSOLUTE_TEMPERATURE_WARNING_C,
            level=None,
        )

    level = LEVEL_WARNING if current.temperature_c >= ABSOLUTE_TEMPERATURE_WARNING_C else None
    return AbsoluteTemperatureResult(
        enough_data=True,
        current_temperature_c=current.temperature_c,
        threshold_c=ABSOLUTE_TEMPERATURE_WARNING_C,
        level=level,
    )


def check_short_term_temperature_rise(
    current: ReportTemperature | None,
    previous: ReportTemperature | None,
) -> ShortTermTemperatureResult:
    """Compare current temperature against the previous report temperature."""
    if current is None or previous is None:
        return ShortTermTemperatureResult(
            enough_data=False,
            current_temperature_c=current.temperature_c if current else None,
            previous_temperature_c=previous.temperature_c if previous else None,
            increase_ratio=None,
            level=None,
        )

    increase_ratio = _temperature_increase_ratio(
        current.temperature_c,
        previous.temperature_c,
    )
    return ShortTermTemperatureResult(
        enough_data=True,
        current_temperature_c=current.temperature_c,
        previous_temperature_c=previous.temperature_c,
        increase_ratio=increase_ratio,
        level=_short_term_level(increase_ratio),
    )


def check_temperature_trend(reports: list[ReportTemperature]) -> TrendTemperatureResult:
    """Use Z-Score and baseline drift checks over the latest 72 reports."""
    unique_reports = _dedupe_report_temperatures(reports)
    if len(unique_reports) < TREND_WINDOW_SIZE:
        current = unique_reports[-1] if unique_reports else None
        return TrendTemperatureResult(
            enough_data=False,
            report_count=len(unique_reports),
            status=None,
            level=None,
            current_temperature_c=current.temperature_c if current else None,
            mean_temperature_c=None,
            sigma_temperature_c=None,
            z_score=None,
            baseline_mean_temperature_c=None,
            recent_mean_temperature_c=None,
            drift_delta_c=None,
            warning=False,
        )

    window = unique_reports[-TREND_WINDOW_SIZE:]
    baseline = [report.temperature_c for report in window[:-1]]
    current_temperature = window[-1].temperature_c
    mean_temperature = sum(baseline) / len(baseline)
    sigma_temperature = _population_sigma(baseline, mean_temperature)
    z_score = _z_score(current_temperature, mean_temperature, sigma_temperature)
    half_window = len(window) // 2
    baseline_mean = _mean_temperature(window[:half_window])
    recent_mean = _mean_temperature(window[half_window:])
    drift_delta = _temperature_delta(recent_mean, baseline_mean)
    z_score_warning = abs(z_score) > TREND_SIGMA_LIMIT
    drift_level = _trend_drift_level(drift_delta)
    level = _max_level(LEVEL_WARNING if z_score_warning else None, drift_level)
    status = _trend_status(z_score_warning, drift_level)
    return TrendTemperatureResult(
        enough_data=True,
        report_count=len(window),
        status=status,
        level=level,
        current_temperature_c=current_temperature,
        mean_temperature_c=mean_temperature,
        sigma_temperature_c=sigma_temperature,
        z_score=z_score,
        baseline_mean_temperature_c=baseline_mean,
        recent_mean_temperature_c=recent_mean,
        drift_delta_c=drift_delta,
        warning=level is not None,
    )


def check_short_window_temperature_rise(
    reports: list[ReportTemperature],
) -> ShortWindowTemperatureResult:
    """Detect short-window warming and high holds with a 0.5°C noise band."""
    unique_reports = _dedupe_report_temperatures(reports)
    if len(unique_reports) < SHORT_WINDOW_MIN_POINTS:
        current = unique_reports[-1] if unique_reports else None
        return ShortWindowTemperatureResult(
            enough_data=False,
            status=None,
            level=None,
            window_count=len(unique_reports),
            window_duration_ms=None,
            start_temperature_c=None,
            current_temperature_c=current.temperature_c if current else None,
            cumulative_delta_c=None,
            latest_delta_c=None,
        )

    window = _short_window_reports(unique_reports)
    if len(window) < SHORT_WINDOW_MIN_POINTS:
        current = window[-1] if window else unique_reports[-1]
        return ShortWindowTemperatureResult(
            enough_data=False,
            status=None,
            level=None,
            window_count=len(window),
            window_duration_ms=_reports_duration_ms(window),
            start_temperature_c=None,
            current_temperature_c=current.temperature_c,
            cumulative_delta_c=None,
            latest_delta_c=None,
        )

    current = window[-1]
    deltas = [
        _temperature_delta(right.temperature_c, left.temperature_c)
        for left, right in zip(window, window[1:], strict=False)
    ]
    latest_delta = deltas[-1]
    start = min(window, key=lambda report: report.temperature_c)
    cumulative_delta = _temperature_delta(current.temperature_c, start.temperature_c)
    window_duration_ms = _reports_duration_ms(window)
    if any(delta <= -TEMP_STABLE_DELTA_C for delta in deltas):
        return ShortWindowTemperatureResult(
            enough_data=True,
            status="回落结束",
            level=None,
            window_count=len(window),
            window_duration_ms=window_duration_ms,
            start_temperature_c=start.temperature_c,
            current_temperature_c=current.temperature_c,
            cumulative_delta_c=cumulative_delta,
            latest_delta_c=latest_delta,
        )

    level = _short_window_level(cumulative_delta)
    status = _short_window_status(deltas, level)
    return ShortWindowTemperatureResult(
        enough_data=True,
        status=status,
        level=level,
        window_count=len(window),
        window_duration_ms=window_duration_ms,
        start_temperature_c=start.temperature_c,
        current_temperature_c=current.temperature_c,
        cumulative_delta_c=cumulative_delta,
        latest_delta_c=latest_delta,
    )


def build_temperature_conclusion(
    absolute: AbsoluteTemperatureResult,
    short_window: ShortWindowTemperatureResult,
    trend: TrendTemperatureResult,
    short_term: ShortTermTemperatureResult,
    peer: PeerComparisonResult,
) -> TemperatureConclusion:
    """Build the overall temperature conclusion from all diagnosis tracks."""
    items = [
        _absolute_temperature_conclusion(absolute),
        _short_window_conclusion(short_window),
        _trend_conclusion(trend),
        _short_term_conclusion(short_term),
        _peer_temperature_conclusion(peer),
    ]
    level = _highest_conclusion_level(items)
    triggered_items = [item for item in items if item.triggered]
    evidence = _conclusion_evidence(items)
    if not triggered_items:
        return TemperatureConclusion(
            level=LEVEL_NORMAL,
            triggered=False,
            conclusion="温度诊断结论：正常",
            evidence=evidence,
            items=items,
        )

    reasons = "；".join(item.conclusion for item in triggered_items)
    return TemperatureConclusion(
        level=level,
        triggered=True,
        conclusion=f"温度诊断结论：{level}，{reasons}",
        evidence=evidence,
        items=items,
    )


def load_recent_report_temperatures(
    sn: str,
    limit: int = RECENT_QUERY_LIMIT,
) -> list[ReportTemperature]:
    """Load recent temperatures from Redis first, then InfluxDB as fallback."""
    cached_points = get_recent_temperature_points(sn, limit=TEMPERATURE_CACHE_LIMIT)
    if len(cached_points) >= TEMPERATURE_CACHE_LIMIT:
        logger.debug(
            "Temperature history loaded from Redis: sn=%s point_count=%s",
            sn,
            len(cached_points),
        )
        return _cache_points_to_reports(cached_points)

    reports = query_recent_report_temperatures_from_influx(sn, limit=limit)
    if reports:
        replace_recent_temperature_points(
            sn,
            _reports_to_cache_points(reports),
            limit=TEMPERATURE_CACHE_LIMIT,
        )
    return reports


def query_recent_report_temperatures_from_influx(
    sn: str,
    limit: int = RECENT_QUERY_LIMIT,
) -> list[ReportTemperature]:
    """Query recent unique report temperatures for one sensor SN."""
    if not sn:
        raise ValueError("sn must be non-empty")

    tables = _query_influx(_build_recent_temperature_query(sn, limit))
    reports = _extract_report_temperatures(tables)
    return sorted(reports, key=_report_sort_ts_ms)


def _log_temperature_result(result: TemperatureDiagnosisResult) -> None:
    logger.info("%s", _format_temperature_conclusion_log(result))

    absolute = result.absolute
    if absolute.enough_data and absolute.level:
        _log_absolute_temperature(result, absolute)
    elif not absolute.enough_data:
        logger.debug(
            "Temperature absolute check skipped: sn=%s report_id=%s not enough data",
            result.sn,
            result.report_id,
        )

    short_term = result.short_term
    if short_term.enough_data and short_term.level:
        _log_short_term_temperature_rise(
            result,
            short_term,
        )
    elif not short_term.enough_data:
        logger.debug(
            "Temperature short-term rise skipped: sn=%s report_id=%s not enough data",
            result.sn,
            result.report_id,
        )

    short_window = result.short_window
    if short_window.enough_data and short_window.level:
        _log_short_window_temperature_rise(result, short_window)
    elif not short_window.enough_data:
        logger.debug(
            "Temperature short-window rise skipped: sn=%s report_id=%s report_count=%s need=%s",
            result.sn,
            result.report_id,
            short_window.window_count,
            SHORT_WINDOW_MIN_POINTS,
        )

    trend = result.trend
    if trend.warning:
        logger.warning(
            "Temperature trend warning: sn=%s report_id=%s current=%s mean=%s sigma=%s "
            "z_score=%.4f",
            result.sn,
            result.report_id,
            trend.current_temperature_c,
            trend.mean_temperature_c,
            trend.sigma_temperature_c,
            trend.z_score,
        )
    elif not trend.enough_data:
        logger.info(
            "Temperature trend skipped: sn=%s report_id=%s report_count=%s need=%s",
            result.sn,
            result.report_id,
            result.report_count,
            TREND_WINDOW_SIZE,
        )


def _format_temperature_conclusion_log(result: TemperatureDiagnosisResult) -> str:
    lines = [
        "Temperature diagnosis conclusion",
        f"  sn: {result.sn}",
        f"  report_id: {result.report_id}",
        f"  report_count: {result.report_count}",
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


def _ensure_current_report_temperature(
    reports: list[ReportTemperature],
    report_id: str,
    current_temperature_c: float,
    current_ts_ms: int,
) -> list[ReportTemperature]:
    if any(report.report_id == report_id for report in reports):
        return reports
    return [
        *reports,
        ReportTemperature(
            report_id=report_id,
            temperature_c=current_temperature_c,
            sort_key=current_ts_ms,
        ),
    ]


def _cache_points_to_reports(points: list[TemperatureCachePoint]) -> list[ReportTemperature]:
    return [
        ReportTemperature(
            report_id=f"redis:{point.ts_ms}",
            temperature_c=point.temp_c,
            sort_key=point.ts_ms,
        )
        for point in points
    ]


def _reports_to_cache_points(reports: list[ReportTemperature]) -> list[TemperatureCachePoint]:
    points: list[TemperatureCachePoint] = []
    for report in reports:
        ts_ms = _sort_key_to_ts_ms(report.sort_key)
        if ts_ms is None:
            continue
        points.append(TemperatureCachePoint(temp_c=report.temperature_c, ts_ms=ts_ms))
    return points


def _sort_key_to_ts_ms(sort_key: Any) -> int | None:
    if isinstance(sort_key, bool):
        return None
    if isinstance(sort_key, int):
        return sort_key
    if isinstance(sort_key, float):
        return int(sort_key)
    if isinstance(sort_key, datetime):
        return int(sort_key.timestamp() * 1000)
    return None


def _log_absolute_temperature(
    result: TemperatureDiagnosisResult,
    absolute: AbsoluteTemperatureResult,
) -> None:
    logger.warning(
        "Temperature absolute warning: sn=%s report_id=%s current=%s threshold=%s",
        result.sn,
        result.report_id,
        absolute.current_temperature_c,
        absolute.threshold_c,
    )


def _log_short_term_temperature_rise(
    result: TemperatureDiagnosisResult,
    short_term: ShortTermTemperatureResult,
) -> None:
    log = logger.info
    if short_term.level == "警告":
        log = logger.warning
    elif short_term.level == "严重":
        log = logger.error

    log(
        "Temperature short-term rise %s: sn=%s report_id=%s previous=%s current=%s "
        "increase_ratio=%.4f",
        short_term.level,
        result.sn,
        result.report_id,
        short_term.previous_temperature_c,
        short_term.current_temperature_c,
        short_term.increase_ratio,
    )


def _log_short_window_temperature_rise(
    result: TemperatureDiagnosisResult,
    short_window: ShortWindowTemperatureResult,
) -> None:
    log = logger.info
    if short_window.level == "警告":
        log = logger.warning
    elif short_window.level == "严重":
        log = logger.error

    log(
        "Temperature short-window rise %s/%s: sn=%s report_id=%s start=%s current=%s "
        "cumulative_delta_c=%.4f latest_delta_c=%.4f window_count=%s",
        short_window.status,
        short_window.level,
        result.sn,
        result.report_id,
        short_window.start_temperature_c,
        short_window.current_temperature_c,
        short_window.cumulative_delta_c,
        short_window.latest_delta_c,
        short_window.window_count,
    )


def _absolute_temperature_conclusion(
    absolute: AbsoluteTemperatureResult,
) -> TemperatureCheckConclusion:
    name = "绝对温度"
    if not absolute.enough_data:
        return TemperatureCheckConclusion(
            name=name,
            level=LEVEL_NOT_CHECKED,
            triggered=False,
            conclusion="绝对温度检测数据不足",
            evidence=[
                "current_temperature_c=N/A",
                f"threshold_c={_format_temperature_value(absolute.threshold_c)}",
                "rule=current_temperature_c >= threshold_c",
            ],
        )
    if absolute.level:
        return TemperatureCheckConclusion(
            name=name,
            level=absolute.level,
            triggered=True,
            conclusion=(
                f"绝对温度过高，当前温度 "
                f"{_format_temperature_value(absolute.current_temperature_c)}°C，"
                f"达到报警阈值 {_format_temperature_value(absolute.threshold_c)}°C"
            ),
            evidence=[
                f"current_temperature_c={_format_temperature_value(absolute.current_temperature_c)}",
                f"threshold_c={_format_temperature_value(absolute.threshold_c)}",
                "rule=current_temperature_c >= threshold_c",
            ],
        )
    return TemperatureCheckConclusion(
        name=name,
        level=LEVEL_NORMAL,
        triggered=False,
        conclusion=(
            f"绝对温度未达到报警阈值 "
            f"{_format_temperature_value(absolute.threshold_c)}°C"
        ),
        evidence=[
            f"current_temperature_c={_format_temperature_value(absolute.current_temperature_c)}",
            f"threshold_c={_format_temperature_value(absolute.threshold_c)}",
            "rule=current_temperature_c < threshold_c",
        ],
    )


def _short_window_conclusion(
    short_window: ShortWindowTemperatureResult,
) -> TemperatureCheckConclusion:
    name = "短窗口"
    if not short_window.enough_data:
        return TemperatureCheckConclusion(
            name=name,
            level=LEVEL_NOT_CHECKED,
            triggered=False,
            conclusion=(
                f"短窗口检测数据不足，当前 {short_window.window_count} 个点，"
                f"至少需要 {SHORT_WINDOW_MIN_POINTS} 个点"
            ),
            evidence=[
                f"window_count={short_window.window_count}",
                f"required_min_points={SHORT_WINDOW_MIN_POINTS}",
                f"current_temperature_c={_format_temperature_value(short_window.current_temperature_c)}",
            ],
        )
    if short_window.level:
        status = short_window.status or "升温"
        return TemperatureCheckConclusion(
            name=name,
            level=short_window.level,
            triggered=True,
            conclusion=(
                f"短窗口{status}，累计升温 "
                f"{_format_temperature_value(short_window.cumulative_delta_c)}°C，"
                f"最新周期变化 {_format_temperature_value(short_window.latest_delta_c)}°C"
            ),
            evidence=[
                f"status={status}",
                f"window_count={short_window.window_count}",
                f"window_duration_ms={_format_temperature_value(short_window.window_duration_ms)}",
                f"start_temperature_c={_format_temperature_value(short_window.start_temperature_c)}",
                f"current_temperature_c={_format_temperature_value(short_window.current_temperature_c)}",
                f"cumulative_delta_c={_format_temperature_value(short_window.cumulative_delta_c)}",
                f"latest_delta_c={_format_temperature_value(short_window.latest_delta_c)}",
                f"attention_delta_c={_format_temperature_value(SHORT_WINDOW_ATTENTION_DELTA_C)}",
                f"warning_delta_c={_format_temperature_value(SHORT_WINDOW_WARNING_DELTA_C)}",
                f"severe_delta_c={_format_temperature_value(SHORT_WINDOW_SEVERE_DELTA_C)}",
            ],
        )
    if short_window.latest_delta_c is not None and short_window.latest_delta_c <= 0:
        conclusion = "当前周期未升温，短窗口检测未触发"
    else:
        conclusion = "短窗口累计升温未达到阈值或窗口内存在明显回落"
    return TemperatureCheckConclusion(
        name=name,
        level=LEVEL_NORMAL,
        triggered=False,
        conclusion=conclusion,
        evidence=[
            f"status={_format_optional_value(short_window.status)}",
            f"window_count={short_window.window_count}",
            f"window_duration_ms={_format_temperature_value(short_window.window_duration_ms)}",
            f"start_temperature_c={_format_temperature_value(short_window.start_temperature_c)}",
            f"current_temperature_c={_format_temperature_value(short_window.current_temperature_c)}",
            f"cumulative_delta_c={_format_temperature_value(short_window.cumulative_delta_c)}",
            f"latest_delta_c={_format_temperature_value(short_window.latest_delta_c)}",
            f"attention_delta_c={_format_temperature_value(SHORT_WINDOW_ATTENTION_DELTA_C)}",
            f"stable_delta_c={_format_temperature_value(TEMP_STABLE_DELTA_C)}",
        ],
    )


def _trend_conclusion(trend: TrendTemperatureResult) -> TemperatureCheckConclusion:
    name = "长窗口"
    if not trend.enough_data:
        return TemperatureCheckConclusion(
            name=name,
            level=LEVEL_NOT_CHECKED,
            triggered=False,
            conclusion=f"长窗口检测数据不足，至少需要 {TREND_WINDOW_SIZE} 个点",
            evidence=[
                f"report_count={trend.report_count}",
                f"required_window_size={TREND_WINDOW_SIZE}",
                f"current_temperature_c={_format_temperature_value(trend.current_temperature_c)}",
            ],
        )
    if trend.warning:
        return TemperatureCheckConclusion(
            name=name,
            level=trend.level or LEVEL_WARNING,
            triggered=True,
            conclusion=(
                f"长窗口{trend.status or '统计异常'}，当前温度 "
                f"{_format_temperature_value(trend.current_temperature_c)}°C，"
                f"z_score={_format_temperature_value(trend.z_score)}，"
                f"慢性漂移 {_format_temperature_value(trend.drift_delta_c)}°C"
            ),
            evidence=[
                f"status={_format_optional_value(trend.status)}",
                f"report_count={trend.report_count}",
                f"current_temperature_c={_format_temperature_value(trend.current_temperature_c)}",
                f"mean_temperature_c={_format_temperature_value(trend.mean_temperature_c)}",
                f"sigma_temperature_c={_format_temperature_value(trend.sigma_temperature_c)}",
                f"z_score={_format_temperature_value(trend.z_score)}",
                f"sigma_limit={_format_temperature_value(TREND_SIGMA_LIMIT)}",
                f"z_score_triggered={abs(trend.z_score or 0) > TREND_SIGMA_LIMIT}",
                f"baseline_mean_temperature_c={_format_temperature_value(trend.baseline_mean_temperature_c)}",
                f"recent_mean_temperature_c={_format_temperature_value(trend.recent_mean_temperature_c)}",
                f"drift_delta_c={_format_temperature_value(trend.drift_delta_c)}",
                f"drift_attention_delta_c={_format_temperature_value(TREND_DRIFT_ATTENTION_DELTA_C)}",
                f"drift_warning_delta_c={_format_temperature_value(TREND_DRIFT_WARNING_DELTA_C)}",
                f"drift_severe_delta_c={_format_temperature_value(TREND_DRIFT_SEVERE_DELTA_C)}",
                f"drift_triggered={_trend_drift_level(trend.drift_delta_c or 0) is not None}",
                "rule=abs(z_score) > sigma_limit",
                "rule=recent_mean_temperature_c - baseline_mean_temperature_c >= drift_threshold",
            ],
        )
    return TemperatureCheckConclusion(
        name=name,
        level=LEVEL_NORMAL,
        triggered=False,
        conclusion="长窗口统计未发现异常",
        evidence=[
            f"report_count={trend.report_count}",
            f"current_temperature_c={_format_temperature_value(trend.current_temperature_c)}",
            f"mean_temperature_c={_format_temperature_value(trend.mean_temperature_c)}",
            f"sigma_temperature_c={_format_temperature_value(trend.sigma_temperature_c)}",
            f"z_score={_format_temperature_value(trend.z_score)}",
            f"sigma_limit={_format_temperature_value(TREND_SIGMA_LIMIT)}",
            f"z_score_triggered={abs(trend.z_score or 0) > TREND_SIGMA_LIMIT}",
            f"baseline_mean_temperature_c={_format_temperature_value(trend.baseline_mean_temperature_c)}",
            f"recent_mean_temperature_c={_format_temperature_value(trend.recent_mean_temperature_c)}",
            f"drift_delta_c={_format_temperature_value(trend.drift_delta_c)}",
            f"drift_attention_delta_c={_format_temperature_value(TREND_DRIFT_ATTENTION_DELTA_C)}",
            f"drift_triggered={_trend_drift_level(trend.drift_delta_c or 0) is not None}",
            "rule=abs(z_score) <= sigma_limit",
            "rule=recent_mean_temperature_c - baseline_mean_temperature_c < drift_threshold",
        ],
    )


def _short_term_conclusion(
    short_term: ShortTermTemperatureResult,
) -> TemperatureCheckConclusion:
    name = "单次检测温度抬升"
    if not short_term.enough_data:
        return TemperatureCheckConclusion(
            name=name,
            level=LEVEL_NOT_CHECKED,
            triggered=False,
            conclusion="单次检测温度抬升数据不足",
            evidence=[
                f"previous_temperature_c={_format_temperature_value(short_term.previous_temperature_c)}",
                f"current_temperature_c={_format_temperature_value(short_term.current_temperature_c)}",
            ],
        )
    if short_term.level:
        return TemperatureCheckConclusion(
            name=name,
            level=short_term.level,
            triggered=True,
            conclusion=(
                f"单次检测温度抬升{short_term.level}，"
                f"从 {_format_temperature_value(short_term.previous_temperature_c)}°C "
                f"升至 {_format_temperature_value(short_term.current_temperature_c)}°C，"
                f"升幅 {_format_ratio(short_term.increase_ratio)}"
            ),
            evidence=[
                f"previous_temperature_c={_format_temperature_value(short_term.previous_temperature_c)}",
                f"current_temperature_c={_format_temperature_value(short_term.current_temperature_c)}",
                f"increase_ratio={_format_ratio(short_term.increase_ratio)}",
                f"attention_ratio={_format_ratio(SHORT_TERM_ATTENTION_RATIO)}",
                f"warning_ratio={_format_ratio(SHORT_TERM_WARNING_RATIO)}",
                f"severe_ratio={_format_ratio(SHORT_TERM_SEVERE_RATIO)}",
            ],
        )
    return TemperatureCheckConclusion(
        name=name,
        level=LEVEL_NORMAL,
        triggered=False,
        conclusion="单次检测温度抬升未达到阈值",
        evidence=[
            f"previous_temperature_c={_format_temperature_value(short_term.previous_temperature_c)}",
            f"current_temperature_c={_format_temperature_value(short_term.current_temperature_c)}",
            f"increase_ratio={_format_ratio(short_term.increase_ratio)}",
            f"attention_ratio={_format_ratio(SHORT_TERM_ATTENTION_RATIO)}",
        ],
    )


def _peer_temperature_conclusion(peer: PeerComparisonResult) -> TemperatureCheckConclusion:
    name = "同组温度横向比较"
    evidence = [
        f"field={peer.field}",
        f"enabled={peer.enabled}",
        f"enough_data={peer.enough_data}",
        f"reason={_format_optional_value(peer.reason)}",
        f"current_temperature_c={_format_temperature_value(peer.current_value)}",
        f"peer_count={peer.peer_count}",
        f"peer_median_temperature_c={_format_temperature_value(peer.peer_median)}",
        f"delta_c={_format_temperature_value(peer.delta)}",
        f"relative_delta={_format_ratio(peer.relative_delta)}",
        f"relative_attention={_format_ratio(PEER_TEMPERATURE_THRESHOLDS.relative_attention)}",
        f"relative_warning={_format_ratio(PEER_TEMPERATURE_THRESHOLDS.relative_warning)}",
        f"relative_severe={_format_ratio(PEER_TEMPERATURE_THRESHOLDS.relative_severe)}",
        f"absolute_attention_c={_format_temperature_value(PEER_TEMPERATURE_THRESHOLDS.absolute_attention)}",
        f"absolute_warning_c={_format_temperature_value(PEER_TEMPERATURE_THRESHOLDS.absolute_warning)}",
        f"absolute_severe_c={_format_temperature_value(PEER_TEMPERATURE_THRESHOLDS.absolute_severe)}",
    ]
    if not peer.enabled or not peer.enough_data:
        return TemperatureCheckConclusion(
            name=name,
            level=LEVEL_NOT_CHECKED,
            triggered=False,
            conclusion="同组温度横向比较数据不足",
            evidence=evidence,
        )
    if peer.level is None:
        return TemperatureCheckConclusion(
            name=name,
            level=LEVEL_NORMAL,
            triggered=False,
            conclusion="同组温度横向比较未见明显偏高",
            evidence=[*evidence, "rule=peer_delta below attention threshold"],
        )
    return TemperatureCheckConclusion(
        name=name,
        level=peer.level,
        triggered=True,
        conclusion=(
            f"同组温度横向比较偏高，当前温度 "
            f"{_format_temperature_value(peer.current_value)}°C，"
            f"同组中位数 {_format_temperature_value(peer.peer_median)}°C，"
            f"偏高 {_format_temperature_value(peer.delta)}°C"
        ),
        evidence=[*evidence, "rule=peer_delta >= level threshold"],
    )


def _highest_conclusion_level(items: list[TemperatureCheckConclusion]) -> str:
    level = LEVEL_NORMAL
    for item in items:
        if CONCLUSION_LEVEL_ORDER.get(item.level, 0) > CONCLUSION_LEVEL_ORDER[level]:
            level = item.level
    return level


def _conclusion_evidence(items: list[TemperatureCheckConclusion]) -> list[str]:
    evidence: list[str] = []
    for item in items:
        item_status = "triggered" if item.triggered else "not_triggered"
        evidence.append(f"{item.name}: level={item.level}, status={item_status}")
        for detail in item.evidence:
            evidence.append(f"{item.name}: {detail}")
    return evidence


def _format_temperature_value(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _format_optional_value(value: str | None) -> str:
    return value if value is not None else "N/A"


def _format_ratio(value: float | None) -> str:
    if value is None:
        return "N/A"
    if value == float("inf"):
        return "inf"
    return f"{value:.2%}"


def _short_term_level(increase_ratio: float) -> str | None:
    if increase_ratio > SHORT_TERM_SEVERE_RATIO:
        return "严重"
    if increase_ratio > SHORT_TERM_WARNING_RATIO:
        return "警告"
    if increase_ratio > SHORT_TERM_ATTENTION_RATIO:
        return "关注"
    return None


def _short_window_level(cumulative_delta_c: float) -> str | None:
    if cumulative_delta_c >= SHORT_WINDOW_SEVERE_DELTA_C:
        return "严重"
    if cumulative_delta_c >= SHORT_WINDOW_WARNING_DELTA_C:
        return "警告"
    if cumulative_delta_c >= SHORT_WINDOW_ATTENTION_DELTA_C:
        return "关注"
    return None


def _trend_drift_level(drift_delta_c: float) -> str | None:
    if drift_delta_c >= TREND_DRIFT_SEVERE_DELTA_C:
        return LEVEL_SEVERE
    if drift_delta_c >= TREND_DRIFT_WARNING_DELTA_C:
        return LEVEL_WARNING
    if drift_delta_c >= TREND_DRIFT_ATTENTION_DELTA_C:
        return LEVEL_ATTENTION
    return None


def _short_window_status(deltas: list[float], level: str | None) -> str | None:
    if level is None:
        return None
    latest_delta = deltas[-1]
    has_clear_prior_rise = any(delta >= TEMP_STABLE_DELTA_C for delta in deltas[:-1])
    if has_clear_prior_rise and latest_delta < TEMP_STABLE_DELTA_C:
        return "高位保持"
    if latest_delta > -TEMP_STABLE_DELTA_C:
        return "持续升温"
    return "回落结束"


def _trend_status(z_score_warning: bool, drift_level: str | None) -> str | None:
    if z_score_warning and drift_level:
        return "统计异常+慢性漂移"
    if z_score_warning:
        return "统计异常"
    if drift_level:
        return "慢性漂移"
    return None


def _max_level(*levels: str | None) -> str | None:
    max_level: str | None = None
    for level in levels:
        if level is None:
            continue
        if max_level is None:
            max_level = level
            continue
        if CONCLUSION_LEVEL_ORDER[level] > CONCLUSION_LEVEL_ORDER[max_level]:
            max_level = level
    return max_level


def _short_window_reports(reports: list[ReportTemperature]) -> list[ReportTemperature]:
    current_ts_ms = _sort_key_to_ts_ms(reports[-1].sort_key)
    if current_ts_ms is None:
        return reports[-SHORT_WINDOW_SIZE:]

    window = [
        report
        for report in reports
        if (ts_ms := _sort_key_to_ts_ms(report.sort_key)) is not None
        and current_ts_ms - ts_ms <= SHORT_WINDOW_DURATION_MS
    ]
    if len(window) >= SHORT_WINDOW_MIN_POINTS:
        return window
    return reports[-SHORT_WINDOW_SIZE:]


def _reports_duration_ms(reports: list[ReportTemperature]) -> int | None:
    if len(reports) < 2:
        return None
    start_ts_ms = _sort_key_to_ts_ms(reports[0].sort_key)
    end_ts_ms = _sort_key_to_ts_ms(reports[-1].sort_key)
    if start_ts_ms is None or end_ts_ms is None:
        return None
    return max(0, end_ts_ms - start_ts_ms)


def _mean_temperature(reports: list[ReportTemperature]) -> float:
    return sum(report.temperature_c for report in reports) / len(reports)


def _temperature_increase_ratio(current_temperature: float, previous_temperature: float) -> float:
    if previous_temperature == 0:
        if current_temperature > 0:
            return float("inf")
        return 0.0
    return (current_temperature - previous_temperature) / abs(previous_temperature)


def _temperature_delta(current_temperature: float, previous_temperature: float) -> float:
    return round(current_temperature - previous_temperature, 4)


def _population_sigma(values: list[float], mean_value: float) -> float:
    variance = sum((value - mean_value) ** 2 for value in values) / len(values)
    return sqrt(variance)


def _z_score(value: float, mean_value: float, sigma: float) -> float:
    if sigma == 0:
        if value == mean_value:
            return 0.0
        return float("inf") if value > mean_value else float("-inf")
    return (value - mean_value) / sigma


def _build_recent_temperature_query(sn: str, limit: int) -> str:
    from app.config import settings

    escaped_sn = _escape_flux_string(sn)
    escaped_bucket = _escape_flux_string(settings.influx_bucket)
    return f'''
        from(bucket:"{escaped_bucket}")
            |> range(start: 0)
            |> filter(fn: (r) => r._measurement == "{MEASUREMENT}")
            |> filter(fn: (r) => r.sn == "{escaped_sn}")
            |> filter(fn: (r) => r._field == "{TEMPERATURE_FIELD}")
            |> group(columns: ["report_id"])
            |> sort(columns: ["_time"], desc: true)
            |> first()
            |> group()
            |> sort(columns: ["_time"], desc: true)
            |> limit(n: {limit})
    '''


def _query_influx(query: str) -> Any:
    from app.config import settings
    from app.database import influxdb_manager

    client = influxdb_manager.get_client()
    query_api = client.query_api()
    return query_api.query(org=settings.influx_org, query=query)


def _extract_report_temperatures(tables: Any) -> list[ReportTemperature]:
    reports: list[ReportTemperature] = []
    for table in tables:
        for record in getattr(table, "records", []):
            values = getattr(record, "values", None)
            if not isinstance(values, dict):
                continue
            report_id = values.get("report_id")
            if not isinstance(report_id, str) or not report_id:
                continue
            temperature = _record_value(record, values)
            if temperature is None:
                continue
            reports.append(
                ReportTemperature(
                    report_id=report_id,
                    temperature_c=temperature,
                    sort_key=_record_sort_key(record, values),
                )
            )
    return _dedupe_report_temperatures(reports)


def _dedupe_report_temperatures(reports: list[ReportTemperature]) -> list[ReportTemperature]:
    deduped: dict[str, ReportTemperature] = {}
    for report in sorted(reports, key=_report_sort_ts_ms):
        deduped[report.report_id] = report
    return list(deduped.values())


def _report_sort_ts_ms(report: ReportTemperature) -> int:
    return _sort_key_to_ts_ms(report.sort_key) or 0


def _find_report_index(reports: list[ReportTemperature], report_id: str) -> int | None:
    for index, report in enumerate(reports):
        if report.report_id == report_id:
            return index
    return None


def _record_value(record: Any, values: dict[str, Any]) -> float | None:
    if hasattr(record, "get_value"):
        value = record.get_value()
    else:
        value = values.get("_value")
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    return None


def _record_sort_key(record: Any, values: dict[str, Any]) -> Any:
    if hasattr(record, "get_time"):
        return record.get_time()
    return values.get("_time", 0)


def _escape_flux_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
