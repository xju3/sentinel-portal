"""
Quick task dispatch for newly uploaded sensor data.

This service runs in the API upload request path. It must stay cheap: compare
the current payload with Redis' last regular snapshot, create at most one
collection task, and return the pending tasks that should be sent to ESP32.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from numbers import Real
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from pub.services.quick_history_cache import (
    QuickDiagnosisSnapshot,
    build_quick_diagnosis_snapshot,
    get_last_regular_snapshot,
)
from pub.services.sensor_task_service import (
    DEFAULT_DENSE_FOCUS_GENERAL,
    SensorTaskSpec,
    build_default_dense_collection_spec,
    build_iis3dwb_parameterized_collection_spec,
    create_collection_task,
    dispatch_pending_sensor_tasks,
    record_sensor_task_report,
)

logger = logging.getLogger(__name__)

QUICK_INTERVAL_MINUTES = 5
QUICK_REPEAT_COUNT = 3
TEMPERATURE_ABSOLUTE_C = 50.0
TEMPERATURE_DELTA_C = 3.0
TEMPERATURE_RELATIVE_DELTA = 0.15
RMS_ABSOLUTE_MM_S = 4.5
RMS_DELTA_MM_S = 1.0
RMS_RELATIVE_DELTA = 0.35
PARAMETERIZED_FFT_POINTS_MULTIPLIER = 2
ALLOWED_IIS3DWB_RANGES = (2, 4, 8, 16)


@dataclass(frozen=True)
class QuickDispatchPlan:
    spec: SensorTaskSpec | None
    reasons: list[str]
    skipped_reason: str | None = None

    @property
    def should_create_task(self) -> bool:
        return self.spec is not None


async def dispatch_quick_diagnosis_tasks(
    *,
    session: AsyncSession,
    report_id: str,
    sn: str,
    payload: dict[str, Any],
) -> list[dict]:
    """Create quick-diagnosis tasks and return pending tasks for the upload response."""
    task_id = _payload_task_id(payload)
    if task_id:
        await record_sensor_task_report(
            session=session,
            task_id=task_id,
            sn=sn,
            sequence=_payload_task_sequence(payload),
            report_id=report_id,
            ts_ms=_payload_ts_ms(payload),
        )
        logger.debug(
            "Quick dispatch skipped for task report: sn=%s report_id=%s task_id=%s",
            sn,
            report_id,
            task_id,
        )
        return await dispatch_pending_sensor_tasks(session, sn)

    last_regular = get_last_regular_snapshot(sn)
    plan = build_quick_dispatch_plan(
        report_id=report_id,
        sn=sn,
        payload=payload,
        last_regular=last_regular,
    )
    if plan.should_create_task and plan.spec is not None:
        task = await create_collection_task(
            session=session,
            sn=sn,
            spec=plan.spec,
            reason="; ".join(plan.reasons),
            name="quick_diagnosis_collection",
        )
        logger.info(
            "Quick dispatch task ready: sn=%s report_id=%s task_id=%s action=%s val=%s reasons=%s",
            sn,
            report_id,
            task.id,
            task.action,
            task.val,
            plan.reasons,
        )
    elif plan.skipped_reason:
        logger.debug(
            "Quick dispatch skipped: sn=%s report_id=%s reason=%s",
            sn,
            report_id,
            plan.skipped_reason,
        )

    return await dispatch_pending_sensor_tasks(session, sn)


def build_quick_dispatch_plan(
    *,
    report_id: str,
    sn: str,
    payload: dict[str, Any],
    last_regular: dict[str, Any] | None,
) -> QuickDispatchPlan:
    """Plan quick-dispatch work without touching the database."""
    current = build_quick_diagnosis_snapshot(report_id=report_id, sn=sn, payload=payload)
    if current.is_task_report:
        return QuickDispatchPlan(spec=None, reasons=[], skipped_reason="task report")
    if current.sample_type and current.sample_type != "normal":
        return QuickDispatchPlan(
            spec=None,
            reasons=[],
            skipped_reason=f"sample_type={current.sample_type}",
        )

    reasons: list[str] = []
    needs_default_dense_collection = False

    clipping_reason = _clipping_reason(current)
    if clipping_reason:
        reasons.append(clipping_reason)

    temperature_reason = _temperature_reason(current, last_regular)
    if temperature_reason:
        reasons.append(temperature_reason)
        needs_default_dense_collection = True

    rms_reason = _rms_reason(current, last_regular)
    if rms_reason:
        reasons.append(rms_reason)
        needs_default_dense_collection = True

    if not reasons:
        return QuickDispatchPlan(spec=None, reasons=[], skipped_reason="no quick trigger")

    parameterized_spec = _parameterized_spec_for_clipping(current)
    if parameterized_spec is not None:
        return QuickDispatchPlan(spec=parameterized_spec, reasons=reasons)

    if not needs_default_dense_collection:
        return QuickDispatchPlan(spec=None, reasons=[], skipped_reason="no dispatchable trigger")

    return QuickDispatchPlan(
        spec=build_default_dense_collection_spec(
            interval_minutes=QUICK_INTERVAL_MINUTES,
            repeat_count=QUICK_REPEAT_COUNT,
            focus_type=DEFAULT_DENSE_FOCUS_GENERAL,
        ),
        reasons=reasons,
    )


def _temperature_reason(
    current: QuickDiagnosisSnapshot,
    last_regular: dict[str, Any] | None,
) -> str | None:
    current_temp = current.temperature_c
    if current_temp is None:
        return None
    if current_temp >= TEMPERATURE_ABSOLUTE_C:
        return (
            f"温度达到固定临界值: current_temperature_c={current_temp}, "
            f"threshold_c={TEMPERATURE_ABSOLUTE_C}"
        )

    previous_temp = _float_from_mapping(last_regular, "temperature_c")
    if previous_temp is None:
        return None
    delta = current_temp - previous_temp
    relative = _relative_positive_delta(current_temp, previous_temp)
    if delta >= TEMPERATURE_DELTA_C or (
        relative is not None and relative >= TEMPERATURE_RELATIVE_DELTA
    ):
        return (
            "温度相对上次正常采集快速升高: "
            f"previous_temperature_c={previous_temp}, current_temperature_c={current_temp}, "
            f"delta_c={round(delta, 4)}, relative_delta={_format_optional(relative)}"
        )
    return None


def _rms_reason(
    current: QuickDiagnosisSnapshot,
    last_regular: dict[str, Any] | None,
) -> str | None:
    current_rms = _max_rms(current.rms_vel_mm_s)
    if current_rms is None:
        return None
    if current_rms >= RMS_ABSOLUTE_MM_S:
        return (
            f"RMS达到固定复核值: current_rms_vel_mm_s={current_rms}, "
            f"threshold_mm_s={RMS_ABSOLUTE_MM_S}"
        )

    previous_rms = _max_rms_from_mapping(last_regular)
    if previous_rms is None:
        return None
    delta = current_rms - previous_rms
    relative = _relative_positive_delta(current_rms, previous_rms)
    if delta >= RMS_DELTA_MM_S and relative is not None and relative >= RMS_RELATIVE_DELTA:
        return (
            "RMS相对上次正常采集快速升高: "
            f"previous_rms_vel_mm_s={previous_rms}, current_rms_vel_mm_s={current_rms}, "
            f"delta_mm_s={round(delta, 4)}, relative_delta={_format_optional(relative)}"
        )
    return None


def _clipping_reason(current: QuickDiagnosisSnapshot) -> str | None:
    quality = current.quality
    if not isinstance(quality, dict) or quality.get("clipped") is not True:
        return None
    return (
        "IIS3DWB采样削峰，需要提高量程复采: "
        f"range_g={current.range_g}, requested_range_g={current.requested_range_g}, "
        f"clip_axes={quality.get('clip_axes')}, total_clip_count={quality.get('total_clip_count')}"
    )


def _parameterized_spec_for_clipping(current: QuickDiagnosisSnapshot) -> SensorTaskSpec | None:
    quality = current.quality
    if not isinstance(quality, dict) or quality.get("clipped") is not True:
        return None
    next_range = _next_iis3dwb_range(current.range_g or current.requested_range_g)
    if next_range is None:
        logger.warning(
            "Quick dispatch clipping found no higher IIS3DWB range: sn=%s range_g=%s requested_range_g=%s",
            current.sn,
            current.range_g,
            current.requested_range_g,
        )
        return None
    return build_iis3dwb_parameterized_collection_spec(
        fft_points_multiplier=PARAMETERIZED_FFT_POINTS_MULTIPLIER,
        range_g=next_range,
        interval_minutes=QUICK_INTERVAL_MINUTES,
        repeat_count=QUICK_REPEAT_COUNT,
    )


def _payload_task_id(payload: dict[str, Any]) -> str:
    value = payload.get("task_id")
    if not isinstance(value, str):
        return ""
    return value.strip()


def _payload_task_sequence(payload: dict[str, Any]) -> int | None:
    value = payload.get("task_sequence", payload.get("sequence"))
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _payload_ts_ms(payload: dict[str, Any]) -> int:
    value = payload.get("ts_ms")
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return 0


def _next_iis3dwb_range(current_range: float | None) -> int | None:
    if current_range is None:
        return 8
    current = int(current_range)
    if current < 8:
        return 8
    if current < 16:
        return 16
    return None


def _max_rms(values: dict[str, float]) -> float | None:
    if not values:
        return None
    return max(values.values())


def _max_rms_from_mapping(snapshot: dict[str, Any] | None) -> float | None:
    if not isinstance(snapshot, dict):
        return None
    values = snapshot.get("rms_vel_mm_s")
    if not isinstance(values, dict):
        return None
    numeric_values = [float(value) for value in values.values() if _is_number(value)]
    if not numeric_values:
        return None
    return max(numeric_values)


def _float_from_mapping(mapping: dict[str, Any] | None, key: str) -> float | None:
    if not isinstance(mapping, dict):
        return None
    value = mapping.get(key)
    if not _is_number(value):
        return None
    return float(value)


def _relative_positive_delta(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    delta = current - previous
    if delta <= 0:
        return 0.0
    return delta / abs(previous)


def _is_number(value: Any) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool)


def _format_optional(value: float | None) -> str:
    if value is None:
        return "None"
    return str(round(value, 4))
