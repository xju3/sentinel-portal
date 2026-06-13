"""
Diagnosis entrypoint.
"""

import asyncio
import logging
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from app.handler.energy_impact import run_energy_impact_check
from app.handler.peak_structure import run_peak_structure_check
from app.handler.quality import run_quality_check
from app.handler.temperature import run_temperature_check
from app.handler.vibration_intensity import run_vibration_intensity_check
from pub.services.diagnosis_service import DiagnosisResultService
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
    quality_result = run_quality_check(report_id, sn, payload)
    saved_quality_result = asyncio.run(
        DiagnosisResultService.save_metric_result_managed(
            quality_result,
            report_ts=current_ts_ms,
        )
    )
    if saved_quality_result is None:
        logger.warning(
            "Quality diagnosis result was not saved: report_id=%s sn=%s",
            report_id,
            sn,
        )
    else:
        logger.debug(
            "Quality diagnosis result saved: report_id=%s sn=%s diagnosis_result_id=%s",
            report_id,
            sn,
            saved_quality_result.id,
        )

    if not quality_result.usable:
        logger.warning(
            "Skipping downstream diagnosis because data quality is not usable: report_id=%s sn=%s level=%s",
            report_id,
            sn,
            quality_result.conclusion.level,
        )
        return

    context = _load_diagnosis_context(sn)

    result = run_temperature_check(
        report_id,
        sn,
        current_temperature_c,
        current_ts_ms,
    )
    saved_result = asyncio.run(
        DiagnosisResultService.save_temperature_result_managed(
            result,
            report_ts=current_ts_ms,
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
