"""
Diagnosis entrypoint.
"""

import logging
from concurrent.futures import Future, ThreadPoolExecutor

from app.handler.temperature import run_temperature_check

logger = logging.getLogger(__name__)

_diagnosis_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="dia-diagnosis")


def start_diagnosis_async(
    report_id: str,
    sn: str,
    current_temperature_c: float,
    current_ts_ms: int,
) -> Future[None]:
    """Start diagnosis work in the background."""
    future = _diagnosis_executor.submit(
        run_diagnosis,
        report_id,
        sn,
        current_temperature_c,
        current_ts_ms,
    )
    future.add_done_callback(_log_diagnosis_failure)
    logger.info("Queued diagnosis job for report_id=%s sn=%s", report_id, sn)
    return future


def run_diagnosis(
    report_id: str,
    sn: str,
    current_temperature_c: float,
    current_ts_ms: int,
) -> None:
    """Run one diagnosis job for an already-ingested report."""
    logger.info(
        "Diagnosis job started for report_id=%s sn=%s current_temperature_c=%s ts_ms=%s",
        report_id,
        sn,
        current_temperature_c,
        current_ts_ms,
    )
    run_temperature_check(
        report_id,
        sn,
        current_temperature_c,
        current_ts_ms,
    )
    logger.info("Diagnosis job finished for report_id=%s sn=%s", report_id, sn)


def _log_diagnosis_failure(future: Future[None]) -> None:
    try:
        future.result()
    except Exception:
        logger.exception("Background diagnosis job failed")
