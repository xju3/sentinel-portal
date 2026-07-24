"""
统一的 Redis Key 管理

在此文件中集中定义所有的 Redis Key，方便全局了解 Redis 的使用情况。
每个 Key 应附带明确的注释，说明其用途、存储的数据结构以及是否会过期。
"""

# ==========================================
# 微信相关 (WeChat)
# ==========================================

# 微信扫码绑定缓存 Key
# 格式: wx_scan_{scene}
# 存储内容: 扫码用户的 wx_user_id (str)
# 过期时间: 300秒 (5分钟)
# 作用: 微信开放平台通过二维码场景值将登录/绑定状态通知给后端，前端通过轮询此 Key 获得绑定状态。
REDIS_KEY_WX_SCAN = "wx_scan_{scene}"


# ==========================================
# 传感器相关 (Sensors)
# ==========================================

# 传感器元数据缓存 Key
# 格式: sensor_meta:{sn}
# 存储内容: 包含 sensor_id, location_id, tenant_id, region_id, device_category_id, process_device_id 的 JSON 字符串
# 过期时间: 永久 (目前不考虑强一致性)
# 作用: 在传感器拉取绑定信息时查询并缓存这些元数据。当传感器上传原始数据时，快速从 Redis 补全数据的上下文属性。
REDIS_KEY_SENSOR_META = "sensor_meta:{sn}"

# ==========================================
# 诊断相关 (Diagnosis)
# ==========================================

# 区域环境温度缓存 Key
# 格式: dia:ambient_temperature:{region_id}
# 存储内容: 区域实时环境温度 (float)
REDIS_KEY_DIA_AMBIENT_TEMP = "dia:ambient_temperature:{region_id}"

# 同组设备缓存 Key
# 格式: dia:peer_group:{process_device_id}:{device_category_id}
# 存储内容: 包含 location_id 等信息的 JSON 列表
REDIS_KEY_DIA_PEER_GROUP = "dia:peer_group:{process_device_id}:{device_category_id}"

# 诊断设备上下文缓存 Key
# 格式: dia:device_context:{device_id}
REDIS_KEY_DIA_DEVICE_CONTEXT = "dia:device_context:{device_id}"
