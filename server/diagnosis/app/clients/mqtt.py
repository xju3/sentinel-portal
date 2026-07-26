import logging
import json
from pub.clients.mqtt import MQTTManager
from pub.manager.database import redis_manager
from pub.utils.redis_keys import REDIS_STREAM_DIA_INGEST
from app.config import settings

logger = logging.getLogger(__name__)

# Stream 最大消息数，超出后自动淘汰最旧消息，防止 Redis 内存无限增长
STREAM_MAXLEN = 5000

def on_mqtt_connect(client, userdata, flags, rc, *args):
    """Callback when MQTT connects to the Broker"""
    if rc == 0:
        logger.info("Diagnosis Service connected to MQTT broker successfully.")
        client.subscribe(settings.mqtt_topic)
        logger.info(f"Subscribed to topic: {settings.mqtt_topic}")
    else:
        logger.error(f"Diagnosis Service failed to connect to MQTT broker, return code: {rc}")

def on_mqtt_disconnect(client, userdata, rc, *args):
    """Callback when MQTT disconnects"""
    logger.warning(f"Diagnosis Service disconnected from MQTT broker, return code: {rc}")

def on_mqtt_message(client, userdata, msg):
    """
    Callback when an MQTT message is received.

    仅做一件事：将 {bucket, path} 写入 Redis Stream，立即返回。
    所有耗时处理（MinIO 拉取、InfluxDB 写入、诊断）均由 stream_worker 异步完成。
    """
    try:
        payload_str = msg.payload.decode('utf-8')
        data = json.loads(payload_str)
        bucket = data.get("bucket")
        path = data.get("path")

        if not bucket or not path:
            logger.error(f"Invalid MQTT payload, missing 'bucket' or 'path': {payload_str}")
            return

        redis_client = redis_manager.get_client()
        redis_client.xadd(
            REDIS_STREAM_DIA_INGEST,
            {"bucket": bucket, "path": path},
            maxlen=STREAM_MAXLEN,
            approximate=True,
        )
        logger.debug(f"Enqueued to stream: bucket={bucket}, path={path}")

    except json.JSONDecodeError as e:
        logger.error(f"Failed to decode MQTT message payload: {e}")
    except Exception as e:
        logger.error(f"Error handling MQTT message: {e}", exc_info=True)

dia_mqtt_manager = MQTTManager(
    on_connect_callback=on_mqtt_connect,
    on_message_callback=on_mqtt_message,
    on_disconnect_callback=on_mqtt_disconnect,
)
