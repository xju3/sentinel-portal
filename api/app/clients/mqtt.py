"""
MQTT connection and background listener
"""

import logging
import uuid
from typing import Optional
import paho.mqtt.client as mqtt

from app.config import settings
from app.clients.handler import patrol_msg_handler

logger = logging.getLogger(__name__)


class MQTTManager:
    """Manager for MQTT connection and subscriptions"""

    def __init__(self):
        self.client: Optional[mqtt.Client] = None

    def init(self) -> None:
        """Initialize MQTT connection and start background loop"""
        try:
            client_id = settings.mqtt_client_id
            if settings.mqtt_client_id_unique:
                # Append unique short hex to prevent client collisions
                client_id = f"{client_id}-{uuid.uuid4().hex[:8]}"

            # Determine protocol version
            protocol = mqtt.MQTTv311 if settings.mqtt_protocol_version == "3.1.1" else mqtt.MQTTv5
            
            # Handle compatibility for paho-mqtt >= 2.0.0
            try:
                from paho.mqtt.enums import CallbackAPIVersion
                self.client = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION1, client_id=client_id, protocol=protocol)
            except ImportError:
                # Fallback for paho-mqtt < 2.0.0
                self.client = mqtt.Client(client_id=client_id, protocol=protocol)

            if settings.mqtt_username and settings.mqtt_password:
                self.client.username_pw_set(settings.mqtt_username, settings.mqtt_password)

            self.client.on_connect = self.on_connect
            self.client.on_message = self.on_message
            self.client.on_disconnect = self.on_disconnect

            self.client.connect(settings.mqtt_host, settings.mqtt_port, keepalive=60)
            # Start a background thread to process network traffic and dispatch callbacks
            self.client.loop_start()
            
            logger.info(f"MQTT connection initialized (Host: {settings.mqtt_host}:{settings.mqtt_port})")
        except Exception as e:
            logger.error(f"Failed to initialize MQTT: {e}")
            raise

    def on_connect(self, client, userdata, flags, rc, *args):
        """Callback for when the client receives a CONNACK response from the server."""
        if rc == 0:
            logger.info(f"Connected to MQTT broker successfully. Subscribing to topic: '{settings.mqtt_topic}'")
            client.subscribe(settings.mqtt_topic)
        else:
            logger.error(f"Failed to connect to MQTT broker with return code: {rc}")

    def on_message(self, client, userdata, msg):
        """Callback for when a PUBLISH message is received from the server."""
        try:
            # patrol_msg_handler.handle_message(msg.topic, msg.payload)
            pass
        except Exception as e:
            logger.error(f"Error processing MQTT message on topic {msg.topic}: {e}")

    def on_disconnect(self, client, userdata, rc, *args):
        """Callback for when the client disconnects from the server."""
        logger.info(f"Disconnected from MQTT broker (Return code: {rc})")

    def close(self) -> None:
        """Stop background loop and disconnect"""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            logger.info("MQTT connection closed")


mqtt_manager = MQTTManager()
