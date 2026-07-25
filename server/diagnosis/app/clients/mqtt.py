import logging
import json
import asyncio
from pub.clients.mqtt import MQTTManager
from app.config import settings
from pub.manager.database import minio_manager
from app.preparation.payload import DeviceDiagnosticReport
from app.preparation.ingestion import process_incoming_report

logger = logging.getLogger(__name__)

# This will hold the reference to the main event loop
_main_loop: asyncio.AbstractEventLoop | None = None

def set_main_loop(loop: asyncio.AbstractEventLoop):
    global _main_loop
    _main_loop = loop

def on_mqtt_connect(client, userdata, flags, rc, *args):
    """Callback when MQTT connects to the Broker"""
    if rc == 0:
        logger.info("Diagnosis Service connected to MQTT broker successfully.")
        # Subscribe to the topic
        client.subscribe(settings.mqtt_topic)
        logger.info(f"Subscribed to topic: {settings.mqtt_topic}")
    else:
        logger.error(f"Diagnosis Service failed to connect to MQTT broker, return code: {rc}")

def on_mqtt_disconnect(client, userdata, rc, *args):
    """Callback when MQTT disconnects"""
    logger.warning(f"Diagnosis Service disconnected from MQTT broker, return code: {rc}")

def on_mqtt_message(client, userdata, msg):
    """Callback when an MQTT message is received"""
    if _main_loop is None:
        logger.error("Main event loop is not set for MQTT manager. Cannot process message.")
        return

    try:
        payload_str = msg.payload.decode('utf-8')
        logger.info(f"Received message on topic {msg.topic}: {payload_str}")
        
        data = json.loads(payload_str)
        bucket = data.get("bucket")
        path = data.get("path")
        
        if not bucket or not path:
            logger.error(f"Invalid MQTT payload, missing 'bucket' or 'path': {payload_str}")
            return
            
        # Dispatch the async processing task to the main event loop
        asyncio.run_coroutine_threadsafe(_process_mqtt_message_async(bucket, path), _main_loop)
            
    except json.JSONDecodeError as e:
        logger.error(f"Failed to decode MQTT message payload: {e}")
    except Exception as e:
        logger.error(f"Error handling MQTT message: {e}", exc_info=True)

async def _process_mqtt_message_async(bucket: str, path: str):
    """Asynchronous handler to fetch data from MinIO and trigger diagnosis"""
    try:
        # Fetch file from MinIO
        minio_client = minio_manager.get_client()
        response = None
        try:
            # We use to_thread because minio get_object is a blocking network call
            response = await asyncio.to_thread(minio_client.get_object, bucket, path)
            file_data = await asyncio.to_thread(response.read)
            json_str = file_data.decode('utf-8')
            json_payload = json.loads(json_str)
            
            # Parse into DeviceDiagnosticReport
            report = DeviceDiagnosticReport.model_validate(json_payload)
            
            # Call process_incoming_report
            await process_incoming_report(report)
            
        finally:
            if response is not None:
                response.close()
                response.release_conn()
                
    except Exception as e:
        logger.error(f"Failed to process MQTT message async for {bucket}/{path}: {e}", exc_info=True)

dia_mqtt_manager = MQTTManager(
    on_connect_callback=on_mqtt_connect,
    on_message_callback=on_mqtt_message,
    on_disconnect_callback=on_mqtt_disconnect,
)
