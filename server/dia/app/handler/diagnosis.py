"""
Diagnosis entrypoint.
"""

import asyncio
import logging
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from app.handler.energy_impact import run_energy_impact_check
from app.handler.peak_structure import run_peak_structure_check
from app.handler.quick_history_cache import record_quick_diagnosis_snapshot
from app.handler.temperature import run_temperature_check
from app.handler.vibration_intensity import run_vibration_intensity_check
from pub.services.diagnosis_service import DiagnosisResultService, DiagnosisRecordService
from pub.services.diagnosis_context_service import DiagnosisContextService

logger = logging.getLogger(__name__)

_diagnosis_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="dia-diagnosis")


def start_diagnosis_async(
    report_id: str,
    sn: str,
    current_temperature_c: float,
    current_ts_ms: int,
    payload: dict[str, Any] | None = None,
) -> Future[None]:
    """Start diagnosis work in the background."""
    future = _diagnosis_executor.submit(
        run_diagnosis,
        report_id,
        sn,
        current_temperature_c,
        current_ts_ms,
        payload,
    )
    future.add_done_callback(_log_diagnosis_failure)
    logger.debug("Queued diagnosis job for report_id=%s sn=%s", report_id, sn)
    return future


def run_diagnosis(
    report_id: str,
    sn: str,
    current_temperature_c: float,
    current_ts_ms: int,
    payload: dict[str, Any] | None = None,
) -> None:
    """Run one diagnosis job for an already-ingested report."""
    logger.debug(
        "Diagnosis job started for report_id=%s sn=%s current_temperature_c=%s ts_ms=%s",
        report_id,
        sn,
        current_temperature_c,
        current_ts_ms,
    )
    payload = payload or {}
    quick_snapshot = record_quick_diagnosis_snapshot(
        report_id=report_id,
        sn=sn,
        payload=payload,
    )
    if quick_snapshot is not None:
        logger.debug(
            "Quick diagnosis snapshot cached: report_id=%s sn=%s task_report=%s",
            report_id,
            sn,
            quick_snapshot.is_task_report,
        )
    context = _load_diagnosis_context(sn)

    # Quality has already been checked at the API layer.
    # We only reach here if quality_status == 0 (usable data).

    result = run_temperature_check(
        report_id,
        sn,
        current_temperature_c,
        current_ts_ms,
        context,
    )
    saved_result = asyncio.run(
        DiagnosisResultService.save_temperature_result_managed(
            result,
            report_ts=current_ts_ms,
            context=context,
        )
    )
    if saved_result is None:
        logger.warning(
            "Temperature diagnosis result was not saved: report_id=%s sn=%s",
            report_id,
            sn,
        )
    else:
        logger.debug(
            "Temperature diagnosis result saved: report_id=%s sn=%s diagnosis_result_id=%s",
            report_id,
            sn,
            saved_result.id,
        )

    vibration_results = [
        run_vibration_intensity_check(report_id, sn, payload, context),
        run_energy_impact_check(report_id, sn, payload, context),
        run_peak_structure_check(report_id, sn, payload, context),
    ]
    for vibration_result in vibration_results:
        saved_vibration_result = asyncio.run(
            DiagnosisResultService.save_metric_result_managed(
                vibration_result,
                report_ts=current_ts_ms,
                context=context,
            )
        )
        if saved_vibration_result is None:
            logger.warning(
                "Vibration diagnosis result was not saved: report_id=%s sn=%s metric=%s",
                report_id,
                sn,
                vibration_result.metric,
            )
        else:
            logger.debug(
                "Vibration diagnosis result saved: report_id=%s sn=%s metric=%s diagnosis_result_id=%s",
                report_id,
                sn,
                vibration_result.metric,
                saved_vibration_result.id,
            )

    all_results = [result] + vibration_results
    level_order = {"严重": 4, "警告": 3, "关注": 2, "正常": 1, "未检测": 0}
    
    highest_level = "正常"
    is_anomaly = False
    max_score = 0
    
    for r in all_results:
        lvl = r.conclusion.level
        score = level_order.get(lvl, 0)
        if score > max_score:
            max_score = score
            highest_level = lvl
        if r.conclusion.triggered:
            is_anomaly = True

    asyncio.run(
        DiagnosisRecordService.update_status_managed(
            report_id=report_id,
            status="COMPLETED",
            overall_level=highest_level,
            is_anomaly=is_anomaly,
        )
    )

    logger.debug("Diagnosis job finished for report_id=%s sn=%s", report_id, sn)


def _load_diagnosis_context(sn: str) -> dict[str, Any] | None:
    try:
        return asyncio.run(DiagnosisContextService.get_by_sn_managed(sn))
    except Exception as e:
        logger.error("Failed to load diagnosis context: sn=%s error=%s", sn, e, exc_info=True)
        return None


def _log_diagnosis_failure(future: Future[None]) -> None:
    try:
        future.result()
    except Exception as e:
        logger.exception("Background diagnosis job failed: %s", e or "Unknown error")
