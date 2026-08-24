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

from pub.services.diagnosis.quick_history_cache import (
    QuickDiagnosisSnapshot,
    build_quick_diagnosis_snapshot,
    get_last_regular_snapshot,
)
from pub.services.sensor.sensor_task_service import (
    SensorTaskSpec,
    TASK_PURPOSE_RESAMPLING,
    build_resampling_spec,
    create_resampling_task,
    dispatch_pending_sensor_tasks,
    ensure_resampling_followup_fft_task,
    ensure_daily_fft_task,
    get_sensor_task_report_by_report_id,
    record_sensor_task_report,
    sensor_task_to_device_payload,
)

logger = logging.getLogger(__name__)

RMS_ABSOLUTE_MM_S = 4.5
RMS_DELTA_MM_S = 1.0
RMS_RELATIVE_DELTA = 0.35
KURTOSIS_EARLY_BEARING_THRESHOLD = 4.5


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
        followup_fft_task = None
        sequence = _payload_task_sequence(payload)
        task = await record_sensor_task_report(
            session=session,
            task_id=task_id,
            sn=sn,
            sequence=sequence,
            report_id=report_id,
            ts_ms=_payload_ts_ms(payload),
        )
        if task is None:
            raise ValueError(
                "Task report could not be recorded before diagnosis dispatch: "
                f"task_id={task_id} report_id={report_id} sn={sn}"
            )
        if sequence is None:
            task_report = await get_sensor_task_report_by_report_id(
                session,
                task.id,
                report_id,
            )
            if task_report is None:
                raise RuntimeError(
                    "Task report was not persisted before diagnosis dispatch: "
                    f"task_id={task.id} report_id={report_id}"
                )
            sequence = int(task_report.sequence)
            payload["task_sequence"] = sequence
        logger.debug(
            "Quick dispatch skipped for task report: sn=%s report_id=%s task_id=%s",
            sn,
            report_id,
            task_id,
        )
        if (
            (
                getattr(task, "task_purpose", None) == TASK_PURPOSE_RESAMPLING
                or (
                    getattr(task, "action", None) == 53
                    and int(getattr(task, "val", 0) or 0) == 3
                )
            )
            and sequence is not None
            and sequence >= int(task.val or 0)
        ):
            reasons = _vibration_trigger_reasons(
                payload=payload,
                last_regular=get_last_regular_snapshot(sn),
            )
            if reasons:
                followup_fft_task = await ensure_resampling_followup_fft_task(
                    session=session,
                    resampling_task_id=task.id,
                    reason=(
                        "复采最终确认仍存在振动或早期轴承冲击异常: "
                        + "; ".join(reasons)
                    ),
                )
        payloads = await dispatch_pending_sensor_tasks(session, sn)
        if (
            followup_fft_task is not None
            and int(getattr(followup_fft_task, "status", -1)) == 2
            and not any(
                item.get("id") == str(followup_fft_task.id)
                for item in payloads
            )
        ):
            followup_payload = await sensor_task_to_device_payload(
                session,
                followup_fft_task,
            )
            if followup_payload is not None:
                payloads.append(followup_payload)
        return payloads

    last_regular = get_last_regular_snapshot(sn)
    plan = build_quick_dispatch_plan(
        report_id=report_id,
        sn=sn,
        payload=payload,
        last_regular=last_regular,
    )
    if plan.should_create_task and plan.spec is not None:
        task = await create_resampling_task(
            session=session,
            sn=sn,
            reason="; ".join(plan.reasons),
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
        if plan.skipped_reason == "no quick trigger":
            await ensure_daily_fft_task(session=session, sn=sn)

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

    reasons = _vibration_trigger_reasons(
        payload=payload,
        last_regular=last_regular,
    )

    if not reasons:
        return QuickDispatchPlan(spec=None, reasons=[], skipped_reason="no quick trigger")

    return QuickDispatchPlan(
        spec=build_resampling_spec(),
        reasons=reasons,
    )


def _vibration_trigger_reasons(
    *,
    payload: dict[str, Any],
    last_regular: dict[str, Any] | None,
) -> list[str]:
    current = build_quick_diagnosis_snapshot(
        report_id="task-decision",
        sn="task-decision",
        payload=payload,
    )
    reasons: list[str] = []
    rms_reason = _rms_reason(current, last_regular)
    if rms_reason:
        reasons.append(rms_reason)
    reasons.extend(_early_bearing_reasons(payload))
    return reasons


def _early_bearing_reasons(payload: dict[str, Any]) -> list[str]:
    axis_features = payload.get("axis_features")
    if not isinstance(axis_features, dict):
        return []

    reasons: list[str] = []
    for axis in ("X", "Y", "Z"):
        axis_payload = axis_features.get(axis)
        if not isinstance(axis_payload, dict):
            continue
        time_payload = axis_payload.get("time")
        if not isinstance(time_payload, dict):
            continue
        kurtosis = time_payload.get("kurtosis")
        if (
            _is_number(kurtosis)
            and float(kurtosis) > KURTOSIS_EARLY_BEARING_THRESHOLD
        ):
            reasons.append(
                f"{axis}轴峭度提示早期轴承冲击: "
                f"kurtosis={float(kurtosis):.4f}, "
                f"threshold={KURTOSIS_EARLY_BEARING_THRESHOLD}"
            )
    return reasons


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




def _payload_task_id(payload: dict[str, Any]) -> str:
    value = payload.get("task_id")
    if not isinstance(value, str):
        return ""
    task_id = value.strip()
    # Firmware uses the sentinel value "0" for anomaly-triggered wakeups.
    # It is not a server SensorTask UUID and must still enter quick diagnosis.
    return "" if task_id == "0" else task_id


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
