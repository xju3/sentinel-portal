import logging
from typing import Any

from app.preparation.payload import DeviceDiagnosticReport

logger = logging.getLogger(__name__)

# In a real scenario, this would be a Redis queue or similar message broker.
# For demonstration purposes, we are defining a placeholder function.
def dispatch_diagnosis_trigger(device_id: str, trigger_ts: int) -> None:
    """
    Push a message to the diagnosis queue indicating that all data for this batch
    has been collected (because total=0 was received) and diagnosis can begin.
    """
    logger.info(
        "TRIGGER DIAGNOSIS: Sent trigger to queue for device_id=%s at ts=%s",
        device_id,
        trigger_ts,
    )


import asyncio
from app.services.context import DeviceContextService

def resolve_location_id(device_id: str, sensor_sn: str) -> str | None:
    """
    Look up the current active measuring point (location_id) 
    for this device and sensor using the DeviceContextService.
    """
    # Use the async context service in a synchronous context for this dummy code, 
    # but in a real async FastAPI app, we would `await` it directly.
    # context = await DeviceContextService.get_by_device_id_managed(device_id)
    
    # Simulating the context fetch
    logger.debug("Resolving location_id for device=%s, sensor=%s via DeviceContextService", device_id, sensor_sn)
    return "resolved_location_uuid_from_context"

def process_incoming_report(report: DeviceDiagnosticReport) -> None:
    """
    Process an incoming diagnostic report from the edge/hardware.
    """
    logger.info(
        "Received report: id=%s, device_id=%s, sensor_sn=%s, ts_ms=%s, delay=%s, total=%s",
        report.report_id,
        report.device_id,
        report.sensor_sn,
        report.ts_ms,
        report.delay,
        report.total,
    )

    # 1. Store the raw/time-series data.
    # TODO: Insert raw waveform data into InfluxDB and update MySQL SensorStatus.
    logger.debug("Simulating data storage for report_id=%s...", report.report_id)

    # 2. Check if we should trigger diagnosis.
    # The condition is that total == 0, meaning all delayed/backfilled historical
    # packets (if any) have been received and we've reached the end of the batch.
    if report.total == 0:
        logger.info(
            "Batch complete (total=0) for device_id=%s. Triggering background diagnosis.",
            report.device_id,
        )
        dispatch_diagnosis_trigger(
            device_id=report.device_id,
            trigger_ts=report.report_ts,
        )
    else:
        logger.debug(
            "Data buffered. Waiting for %s more packets before triggering diagnosis for device_id=%s",
            report.total,
            report.device_id,
        )
