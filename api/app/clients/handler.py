"""
MQTT message handler
"""

import logging
import json
from typing import Optional

from app.models.message_pb2 import MsgRmsReport
from app.clients.redis import redis_client
from app.diagnosis.patrol_diagnosis import patrol_diagnostic_engine

logger = logging.getLogger(__name__)


class PatrolMsgHandler:
    """Handler for patrol (巡检) MQTT messages.

    Parses protobuf-encoded MsgRmsReport messages and pushes
    the relevant data (rms_m, temperature) into a Redis queue.
    """

    def __init__(self) -> None:
        self._redis_client = redis_client

    def _parse_payload(self, payload: bytes) -> Optional[MsgRmsReport]:
        """Parse the protobuf payload into a MsgRmsReport message.

        Args:
            payload: The raw message payload (bytes).

        Returns:
            A MsgRmsReport instance, or None if parsing fails.
        """
        try:
            report = MsgRmsReport()
            report.ParseFromString(payload)
            return report
        except Exception as e:
            logger.error(f"Failed to parse protobuf payload: {e}")
            return None

    def handle_message(self, topic: str, payload: bytes) -> None:
        """Handle an incoming MQTT message.

        Parses the protobuf payload to extract the SN, rms_m, and temperature,
        then pushes the data into a fixed-length Redis queue.

        Args:
            topic: The MQTT topic the message was published on.
            payload: The raw message payload (bytes).
        """
        # logger.info(f"[PatrolMsgHandler] Received message on topic '{topic}': {payload}")

        # Parse protobuf payload
        report = self._parse_payload(payload)
        if not report:
            logger.warning("Failed to parse payload")
            return

        sn = str(report.sn)
        logger.info(
            f"Parsed message: SN={sn}, rms_m={report.rms_m}, temperature={report.temperature}"
        )

        # 1. 最新数据进 Redis 72位队列
        success = self._redis_client.push_rms_data(sn, rms_m=report.rms_m, temperature=report.temperature)
        
        # 2. 队列更新成功后，触发极速诊断
        if success:
            temp_report = patrol_diagnostic_engine.run_diagnostics(sn, "temperature")
            rms_report = patrol_diagnostic_engine.run_diagnostics(sn, "rms_m")
            
            # 如果有报警，输出 JSON 日志
            if temp_report["health_status"] != "NORMAL":
                logger.warning(f"【温度报警】\n{json.dumps(temp_report, ensure_ascii=False, indent=2)}")

# Global instance
patrol_msg_handler = PatrolMsgHandler()
