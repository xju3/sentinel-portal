import logging
from pub.clients.mqtt import MQTTManager

logger = logging.getLogger(__name__)


def on_mqtt_connect(client, userdata, flags, rc, *args):
    """MQTT 连上 Broker 时的回调"""
    if rc == 0:
        logger.info("API Service connected to MQTT broker successfully.")
    else:
        logger.error(f"API Service failed to connect to MQTT broker, return code: {rc}")


def on_mqtt_disconnect(client, userdata, rc, *args):
    """MQTT 断开时的回调"""
    logger.warning(f"API Service disconnected from MQTT broker, return code: {rc}")


# 专门为 API 服务实例化的 MQTT 客户端管理器
# 由于 API 在这里只作为数据发布者，不需要订阅 topic，所以不注册 on_message_callback
api_mqtt_manager = MQTTManager(
    on_connect_callback=on_mqtt_connect,
    on_disconnect_callback=on_mqtt_disconnect,
)
