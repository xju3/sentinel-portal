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

Temperature is checked on two tracks:
1. Short-term rise:
   Compare the current report temperature with the previous report for the
   same sensor. If the rise is greater than 10%, log "关注"; greater than 15%,
   log "警告"; greater than 20%, log "严重".
2. Trend rise:
   Read recent unique report temperatures for the same sensor and inject the
   current report temperature if it is not visible in InfluxDB yet. Use the
   latest 72 reports as a sliding window; compare the newest point against the
   previous 71 points with Z-Score / 3-Sigma. If abs(z_score) > 3, log a
   warning.

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
TREND_SIGMA_LIMIT = 3.0


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
    current_temperature_c: float | None
    mean_temperature_c: float | None
    sigma_temperature_c: float | None
    z_score: float | None
    warning: bool


@dataclass(frozen=True)
class TemperatureDiagnosisResult:
    sn: str
    report_id: str
    report_count: int
    short_term: ShortTermTemperatureResult
    trend: TrendTemperatureResult


def run_temperature_check(
    report_id: str,
    sn: str,
    current_temperature_c: float,
    current_ts_ms: int,
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
    result = diagnose_temperature(sn, report_id, reports)
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
) -> TemperatureDiagnosisResult:
    """Run short-term and trend temperature checks from unique report temperatures."""
    unique_reports = _dedupe_report_temperatures(reports)
    current_index = _find_report_index(unique_reports, report_id)
    current_index = current_index if current_index is not None else len(unique_reports) - 1
    current = unique_reports[current_index] if current_index >= 0 else None
    previous = unique_reports[current_index - 1] if current_index > 0 else None

    short_term = check_short_term_temperature_rise(current, previous)
    trend = check_temperature_trend(unique_reports[: current_index + 1])
    return TemperatureDiagnosisResult(
        sn=sn,
        report_id=report_id,
        report_count=len(unique_reports),
        short_term=short_term,
        trend=trend,
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
    """Use a sliding Z-Score/3-Sigma check over the latest 72 reports."""
    unique_reports = _dedupe_report_temperatures(reports)
    if len(unique_reports) < TREND_WINDOW_SIZE:
        current = unique_reports[-1] if unique_reports else None
        return TrendTemperatureResult(
            enough_data=False,
            current_temperature_c=current.temperature_c if current else None,
            mean_temperature_c=None,
            sigma_temperature_c=None,
            z_score=None,
            warning=False,
        )

    window = unique_reports[-TREND_WINDOW_SIZE:]
    baseline = [report.temperature_c for report in window[:-1]]
    current_temperature = window[-1].temperature_c
    mean_temperature = sum(baseline) / len(baseline)
    sigma_temperature = _population_sigma(baseline, mean_temperature)
    z_score = _z_score(current_temperature, mean_temperature, sigma_temperature)
    return TrendTemperatureResult(
        enough_data=True,
        current_temperature_c=current_temperature,
        mean_temperature_c=mean_temperature,
        sigma_temperature_c=sigma_temperature,
        z_score=z_score,
        warning=abs(z_score) > TREND_SIGMA_LIMIT,
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


def _short_term_level(increase_ratio: float) -> str | None:
    if increase_ratio > SHORT_TERM_SEVERE_RATIO:
        return "严重"
    if increase_ratio > SHORT_TERM_WARNING_RATIO:
        return "警告"
    if increase_ratio > SHORT_TERM_ATTENTION_RATIO:
        return "关注"
    return None


def _temperature_increase_ratio(current_temperature: float, previous_temperature: float) -> float:
    if previous_temperature == 0:
        if current_temperature > 0:
            return float("inf")
        return 0.0
    return (current_temperature - previous_temperature) / abs(previous_temperature)


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
