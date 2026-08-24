"""
Redis snapshots for quick task-dispatch decisions.

DIA writes these snapshots at the beginning of deep diagnosis so the API-side
quick dispatcher can compare a new upload with the last regular report without
querying MySQL or InfluxDB.

Keys:
- dia:quick:history:{sn}:recent
  Recent lightweight snapshots. This includes regular reports and task reports.
- dia:quick:last_regular:{sn}
  The latest regular report snapshot. Reports carrying a non-empty task_id do
  not update this key, which prevents task-generated data from becoming the
  baseline for a future quick-dispatch decision.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from numbers import Real
from typing import Any, cast

from pub.manager.database import redis_manager

logger = logging.getLogger(__name__)

QUICK_HISTORY_KEY_PREFIX = "dia:quick:history:"
QUICK_LAST_REGULAR_KEY_PREFIX = "dia:quick:last_regular:"
QUICK_HISTORY_LIMIT = 72
AXES = ("X", "Y", "Z")


@dataclass(frozen=True)
class QuickDiagnosisSnapshot:
    report_id: str
    sn: str
    ts_ms: int | None
    task_id: str
    sample_type: str | None
    temperature_c: float | None
    requested_range_g: float | None
    range_g: float | None
    points: int | None
    fs_hz: int | None
    rms_vel_mm_s: dict[str, float]
    quality: dict[str, Any]

    @property
    def is_task_report(self) -> bool:
        return bool(self.task_id and self.task_id != "0")


def record_quick_diagnosis_snapshot(
    *,
    report_id: str,
    sn: str,
    payload: dict[str, Any],
    limit: int = QUICK_HISTORY_LIMIT,
) -> QuickDiagnosisSnapshot | None:
    """Store a lightweight quick-diagnosis snapshot in Redis.

    The function is intentionally best-effort: Redis failure must not stop deep
    diagnosis or result persistence.
    """
    snapshot = build_quick_diagnosis_snapshot(report_id=report_id, sn=sn, payload=payload)
    client = _get_redis_client()
    if client is None:
        return snapshot

    try:
        raw = _serialize_snapshot(snapshot)
        pipeline = client.pipeline()
        pipeline.lpush(_history_key(sn), raw)
        pipeline.ltrim(_history_key(sn), 0, limit - 1)
        # Anomaly wakeups (task_id="0") participate in quick diagnosis but
        # must not replace the last scheduled regular baseline.
        if not snapshot.task_id:
            pipeline.set(_last_regular_key(sn), raw)
        pipeline.execute()
    except Exception as e:
        logger.warning("Failed to write quick diagnosis Redis snapshot for sn=%s: %s", sn, e)

    return snapshot


def build_quick_diagnosis_snapshot(
    *,
    report_id: str,
    sn: str,
    payload: dict[str, Any],
) -> QuickDiagnosisSnapshot:
    """Build the Redis payload used by quick dispatch and DIA checks."""
    return QuickDiagnosisSnapshot(
        report_id=report_id,
        sn=sn,
        ts_ms=_as_int(payload.get("ts_ms")),
        task_id=_task_id(payload),
        sample_type=payload.get("sample_type") if isinstance(payload.get("sample_type"), str) else None,
        temperature_c=_as_float(payload.get("temperature_c")),
        requested_range_g=_as_float(payload.get("requested_range_g")),
        range_g=_as_float(payload.get("range_g")),
        points=_as_int(payload.get("points")),
        fs_hz=_as_int(payload.get("fs_hz")),
        rms_vel_mm_s=_rms_velocity_by_axis(payload),
        quality=_quality_summary(payload),
    )


def get_last_regular_snapshot(sn: str) -> dict[str, Any] | None:
    """Read the latest regular-report snapshot for one SN."""
    client = _get_redis_client()
    if client is None:
        return None
    try:
        raw = client.get(_last_regular_key(sn))
    except Exception as e:
        logger.warning("Failed to read quick last-regular snapshot for sn=%s: %s", sn, e)
        return None
    return _parse_snapshot(raw)


def get_recent_snapshots(sn: str, limit: int = QUICK_HISTORY_LIMIT) -> list[dict[str, Any]]:
    """Read recent quick snapshots newest first."""
    client = _get_redis_client()
    if client is None:
        return []
    try:
        raw_items = cast(list, client.lrange(_history_key(sn), 0, limit - 1))
    except Exception as e:
        logger.warning("Failed to read quick history snapshots for sn=%s: %s", sn, e)
        return []
    snapshots = [_parse_snapshot(item) for item in raw_items]
    return [snapshot for snapshot in snapshots if snapshot is not None]


def _history_key(sn: str) -> str:
    return f"{QUICK_HISTORY_KEY_PREFIX}{sn}:recent"


def _last_regular_key(sn: str) -> str:
    return f"{QUICK_LAST_REGULAR_KEY_PREFIX}{sn}"


def _get_redis_client() -> Any | None:
    try:
        return redis_manager.get_client()
    except RuntimeError:
        logger.warning("Redis is not initialized; quick diagnosis cache unavailable")
        return None


def _serialize_snapshot(snapshot: QuickDiagnosisSnapshot) -> str:
    return json.dumps(
        {
            "report_id": snapshot.report_id,
            "sn": snapshot.sn,
            "ts_ms": snapshot.ts_ms,
            "task_id": snapshot.task_id,
            "sample_type": snapshot.sample_type,
            "temperature_c": snapshot.temperature_c,
            "requested_range_g": snapshot.requested_range_g,
            "range_g": snapshot.range_g,
            "points": snapshot.points,
            "fs_hz": snapshot.fs_hz,
            "rms_vel_mm_s": snapshot.rms_vel_mm_s,
            "quality": snapshot.quality,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _parse_snapshot(raw: Any) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _task_id(payload: dict[str, Any]) -> str:
    value = payload.get("task_id")
    if not isinstance(value, str):
        return ""
    return value.strip()


def _rms_velocity_by_axis(payload: dict[str, Any]) -> dict[str, float]:
    axis_features = payload.get("axis_features")
    if not isinstance(axis_features, dict):
        return {}

    values: dict[str, float] = {}
    for axis in AXES:
        axis_payload = axis_features.get(axis)
        if not isinstance(axis_payload, dict):
            continue
        time_payload = axis_payload.get("time")
        if not isinstance(time_payload, dict):
            continue
        rms_vel = _as_float(time_payload.get("rms_vel_mm_s"))
        if rms_vel is not None:
            values[axis] = rms_vel
    return values


def _quality_summary(payload: dict[str, Any]) -> dict[str, Any]:
    quality = payload.get("quality")
    if not isinstance(quality, dict):
        return {
            "status": None,
            "auto_range": None,
            "accepted_range_g": None,
            "clipped": False,
            "near_clip": False,
            "total_clip_count": 0,
            "max_clip_ratio": None,
            "max_abs_g": None,
            "clip_axes": [],
            "attempts": [],
        }

    attempts = quality.get("attempts")
    attempt_summaries = []
    if isinstance(attempts, list):
        for attempt in attempts:
            if isinstance(attempt, dict):
                attempt_summaries.append(_attempt_summary(attempt))

    accepted_attempt = next(
        (
            attempt
            for attempt in attempt_summaries
            if attempt.get("accepted") is True
        ),
        None,
    )
    total_clip_count = sum(int(attempt["total_clip_count"]) for attempt in attempt_summaries)
    max_clip_ratio = _max_optional_float(attempt.get("max_clip_ratio") for attempt in attempt_summaries)
    max_abs_g = _max_optional_float(attempt.get("max_abs_g") for attempt in attempt_summaries)
    clip_axes = sorted(
        {
            axis
            for attempt in attempt_summaries
            for axis in attempt.get("clip_axes", [])
            if isinstance(axis, str)
        }
    )
    near_clip = any(bool(attempt.get("near_clip")) for attempt in attempt_summaries)

    return {
        "status": quality.get("status") if isinstance(quality.get("status"), str) else None,
        "auto_range": quality.get("auto_range") if isinstance(quality.get("auto_range"), bool) else None,
        "accepted_range_g": accepted_attempt.get("range_g") if accepted_attempt else None,
        "clipped": total_clip_count > 0 or bool(max_clip_ratio and max_clip_ratio > 0),
        "near_clip": near_clip,
        "total_clip_count": total_clip_count,
        "max_clip_ratio": max_clip_ratio,
        "max_abs_g": max_abs_g,
        "clip_axes": clip_axes,
        "attempts": attempt_summaries,
    }


def _attempt_summary(attempt: dict[str, Any]) -> dict[str, Any]:
    axes = attempt.get("axes")
    total_clip_count = 0
    max_clip_ratio: float | None = None
    max_abs_g: float | None = None
    clip_axes: list[str] = []
    near_clip = False
    clip_threshold_g = _as_float(attempt.get("clip_threshold_g"))

    if isinstance(axes, dict):
        for axis in AXES:
            axis_quality = axes.get(axis)
            if not isinstance(axis_quality, dict):
                continue
            clip_count = _as_int(axis_quality.get("clip_count")) or 0
            clip_ratio = _as_float(axis_quality.get("clip_ratio"))
            axis_max_abs_g = _as_float(axis_quality.get("max_abs_g"))
            total_clip_count += clip_count
            if clip_count > 0 or (clip_ratio is not None and clip_ratio > 0):
                clip_axes.append(axis)
            max_clip_ratio = _max_pair(max_clip_ratio, clip_ratio)
            max_abs_g = _max_pair(max_abs_g, axis_max_abs_g)
            if clip_threshold_g is not None and axis_max_abs_g is not None:
                near_clip = near_clip or axis_max_abs_g >= 0.9 * clip_threshold_g

    return {
        "range_g": _as_float(attempt.get("range_g")),
        "accepted": attempt.get("accepted") if isinstance(attempt.get("accepted"), bool) else None,
        "reason": attempt.get("reason") if isinstance(attempt.get("reason"), str) else None,
        "clip_threshold_g": clip_threshold_g,
        "total_clip_count": total_clip_count,
        "max_clip_ratio": max_clip_ratio,
        "max_abs_g": max_abs_g,
        "clip_axes": clip_axes,
        "near_clip": near_clip,
    }


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, Real):
        return float(value)
    return None


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _max_optional_float(values: Any) -> float | None:
    result: float | None = None
    for value in values:
        result = _max_pair(result, value)
    return result


def _max_pair(left: float | None, right: Any) -> float | None:
    if not isinstance(right, Real) or isinstance(right, bool):
        return left
    value = float(right)
    if left is None or value > left:
        return value
    return left
