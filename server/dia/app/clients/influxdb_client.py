"""
Vibration feature writer for Telegraf/InfluxDB.
"""

import logging
from numbers import Real
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MEASUREMENT = "vibration_feature"
AXES = ("X", "Y", "Z")
TIME_FIELDS = (
    "rms_acc_g",
    "peak_acc_g",
    "peak_to_peak_acc_g",
    "rms_vel_mm_s",
    "crest_factor",
    "kurtosis",
)
BAND_FIELDS = {
    "0_100": "band_0_100",
    "100_500": "band_100_500",
    "500_1000": "band_500_1000",
    "1000_2000": "band_1000_2000",
    "2000_5000": "band_2000_5000",
}


def build_vibration_feature_lines(
    payload: dict[str, Any],
    report_id: str | None = None,
) -> list[str]:
    """Build one line-protocol row per axis from a result.json-compatible payload."""
    sn = _require_str(payload, "sn")
    sample_type = _require_str(payload, "sample_type")
    ts_ms = _require_int(payload, "ts_ms")
    report_id = report_id or _require_str(payload, "report_id")
    axis_features = payload.get("axis_features")
    if not isinstance(axis_features, dict):
        raise ValueError("payload.axis_features must be an object")

    lines = []
    for axis in AXES:
        axis_payload = axis_features.get(axis)
        if not isinstance(axis_payload, dict):
            raise ValueError(f"payload.axis_features.{axis} must be an object")
        fields = _build_axis_fields(payload, axis_payload)
        line = _format_line_protocol(
            measurement=MEASUREMENT,
            tags={
                "report_id": report_id,
                "sn": sn,
                "axis": axis,
                "sample_type": sample_type,
            },
            fields=fields,
            timestamp_ns=ts_ms * 1_000_000,
        )
        lines.append(line)
    return lines


def send_vibration_features_to_telegraf(payload: dict[str, Any]) -> tuple[str, int]:
    """Send vibration feature rows to Telegraf's influx line-protocol listener."""
    from app.config import settings

    report_id = _require_str(payload, "report_id")
    lines = build_vibration_feature_lines(payload, report_id=report_id)
    body = "\n".join(lines) + "\n"
    url = _telegraf_write_url(settings.telegraf_url)
    logger.debug(f"Sending vibration features to Telegraf at {url}")

    with httpx.Client(timeout=10.0) as client:
        response = client.post(
            url,
            content=body.encode("utf-8"),
            headers={"Content-Type": "text/plain; charset=utf-8"},
        )
        response.raise_for_status()

    logger.debug(
        "Wrote %s vibration_feature points to Telegraf for report_id=%s",
        len(lines),
        report_id,
    )
    return report_id, len(lines)


def _build_axis_fields(
    root_payload: dict[str, Any],
    axis_payload: dict[str, Any],
) -> dict[str, float]:
    fields: dict[str, float] = {}
    _put_numeric(fields, "temperature_c", root_payload.get("temperature_c"))

    time_payload = axis_payload.get("time", {})
    if not isinstance(time_payload, dict):
        raise ValueError("axis time features must be an object")
    for field_name in TIME_FIELDS:
        _put_numeric(fields, field_name, time_payload.get(field_name))

    freq_payload = axis_payload.get("freq", {})
    if not isinstance(freq_payload, dict):
        raise ValueError("axis frequency features must be an object")
    _put_numeric(fields, "spectral_centroid_hz", freq_payload.get("spectral_centroid_hz"))
    _put_numeric(fields, "spectral_entropy", freq_payload.get("spectral_entropy"))

    band_payload = axis_payload.get("band_energy_ratio", {})
    if not isinstance(band_payload, dict):
        raise ValueError("axis band_energy_ratio must be an object")
    for source_name, target_name in BAND_FIELDS.items():
        _put_numeric(fields, target_name, band_payload.get(source_name))

    peaks = freq_payload.get("peaks", [])
    if peaks is None:
        peaks = []
    if not isinstance(peaks, list):
        raise ValueError("axis freq.peaks must be a list")
    for index, peak in enumerate(peaks[:5], start=1):
        if not isinstance(peak, dict):
            raise ValueError("axis freq.peaks items must be objects")
        _put_numeric(fields, f"peak{index}_freq_hz", peak.get("freq_hz"))
        _put_numeric(fields, f"peak{index}_amp_g", peak.get("amp_g"))

    if not fields:
        raise ValueError("axis payload did not produce any numeric fields")
    return fields


def _format_line_protocol(
    measurement: str,
    tags: dict[str, str],
    fields: dict[str, float],
    timestamp_ns: int,
) -> str:
    tag_text = ",".join(
        f"{_escape_tag_key(key)}={_escape_tag_value(value)}" for key, value in tags.items()
    )
    field_text = ",".join(
        f"{_escape_field_key(key)}={_format_float(value)}" for key, value in fields.items()
    )
    return f"{_escape_measurement(measurement)},{tag_text} {field_text} {timestamp_ns}"


def _telegraf_write_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/write"):
        return normalized
    return f"{normalized}/write"


def _put_numeric(fields: dict[str, float], name: str, value: Any) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"field {name} must be numeric")
    fields[name] = float(value)


def _require_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"payload.{key} must be a non-empty string")
    return value


def _require_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"payload.{key} must be an integer")
    return value


def _format_float(value: float) -> str:
    return format(value, ".15g")


def _escape_measurement(value: str) -> str:
    return value.replace("\\", "\\\\").replace(",", "\\,").replace(" ", "\\ ")


def _escape_tag_key(value: str) -> str:
    return _escape_measurement(value).replace("=", "\\=")


def _escape_tag_value(value: str) -> str:
    return _escape_tag_key(value)


def _escape_field_key(value: str) -> str:
    return _escape_tag_key(value)
