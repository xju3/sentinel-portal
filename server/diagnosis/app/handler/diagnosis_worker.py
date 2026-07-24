import logging
from typing import Any

logger = logging.getLogger(__name__)

class DiagnosisWorker:
    """
    Background worker that executes diagnosis when triggered by the ingestion layer.
    """

    @staticmethod
    def execute_batch_diagnosis(device_id: str, location_id: str, trigger_ts_ms: int) -> None:
        """
        Triggered when total=0 is received.
        Pulls the complete batch of data and runs the diagnosis sequentially.
        """
        logger.info("Worker started for device=%s, location=%s", device_id, location_id)

        # 1. Fetch the data batch
        # Because the data was stored in InfluxDB using ts_ms as the primary Time index,
        # it is ALREADY perfectly sorted chronologically on disk!
        # We just need to query the range.
        
        # Pseudo InfluxDB Query:
        # SELECT * FROM vibration_features 
        # WHERE device_id = '{device_id}' AND location_id = '{location_id}'
        #   AND time <= {trigger_ts_ms} 
        #   AND time >= {time_of_the_most_recent_delay_0}
        # ORDER BY time ASC
        
        # Simulated data returned by InfluxDB (we only need the latest delay=0 record to run the algorithm)
        # But for calculating slopes, the algorithm internally will query InfluxDB for the past N minutes.
        latest_record = DiagnosisWorker._fetch_latest_record(device_id, location_id, trigger_ts_ms)
        
        if latest_record:
            logger.info("Starting diagnosis for the latest record (delay=0) at ts_ms=%s", latest_record["ts_ms"])
            DiagnosisWorker._run_algorithm(latest_record)

    @staticmethod
    def _fetch_latest_record(device_id: str, location_id: str, trigger_ts_ms: int) -> dict[str, Any]:
        """
        Simulates fetching the latest delay=0 record.
        """
        return {"ts_ms": 1784612273583, "delay": 0, "rms": 1.4}

    @staticmethod
    def _run_algorithm(record: dict[str, Any]) -> None:
        """
        Simulates the actual diagnostic logic (checking thresholds, slope, etc.)
        """
        logger.debug("Diagnosing record at ts_ms=%s (delay=%s)", record["ts_ms"], record["delay"])
