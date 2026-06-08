"""
MQTT connection and background listener
"""

import logging
import uuid
from typing import Optional
import paho.mqtt.client as mqtt

from app.config import settings

logger = logging.getLogger(__name__)


class MQTTManager:
    """Manager for MQTT connection and subscriptions"""

    def __init__(self):
        self.client: Optional[mqtt.Client] = None
        self._on_connect_callbacks = []
        self._on_message_callbacks = []

    def register_on_connect(self, callback) -> None:
        """注册自定义的 on_connect 回调函数"""
        self._on_connect_callbacks.append(callback)

    def register_on_message(self, callback) -> None:
        """注册自定义的 on_message 回调函数"""
        self._on_message_callbacks.append(callback)

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
            logger.info("Connected to MQTT broker successfully.")
            # 执行所有调用者注册的 on_connect 回调（例如：订阅 topic）
            for cb in self._on_connect_callbacks:
                try:
                    cb(client, userdata, flags, rc, *args)
                except Exception as e:
                    logger.error(f"Error in custom on_connect callback: {e}", exc_info=True)
        else:
            logger.error(f"Failed to connect to MQTT broker with return code: {rc}")

    def on_message(self, client, userdata, msg):
        """Callback for when a PUBLISH message is received from the server."""
        # 将收到的消息分发给所有调用者注册的处理函数
        for cb in self._on_message_callbacks:
            try:
                cb(client, userdata, msg)
            except Exception as e:
                logger.error(f"Error in custom on_message callback for topic {msg.topic}: {e}", exc_info=True)

    def on_disconnect(self, client, userdata, rc, *args):
        """Callback for when the client disconnects from the server."""
        logger.info(f"Disconnected from MQTT broker (Return code: {rc})")

    def publish(self, topic: str, payload: str, qos: int = 1) -> bool:
        """向指定的 MQTT topic 发布消息。

        Args:
            topic:   MQTT topic，如 "/sentinel/config/SN001"
            payload: 消息体，JSON 字符串
            qos:     QoS 级别，默认 1（至少一次）

        Returns:
            True 表示发布成功，False 表示失败。
        """
        if self.client is None:
            logger.error(f"MQTT client not initialized, cannot publish to {topic}")
            return False
        try:
            result = self.client.publish(topic, payload, qos=qos)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.debug(f"MQTT published: {topic} -> {payload}")
                return True
            else:
                logger.error(f"MQTT publish failed: {topic}, rc={result.rc}")
                return False
        except Exception as e:
            logger.error(f"MQTT publish exception: {topic}, error={e}")
            return False

    def close(self) -> None:
        """Stop background loop and disconnect"""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            logger.info("MQTT connection closed")


mqtt_manager = MQTTManager()
