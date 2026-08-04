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

# 传感器复采任务序数缓存 Key
# 格式: task:seq:{task_id}
# 存储内容: 当前复采任务执行的次数 (int)
# 过期时间: 24小时 (86400秒)
# 作用: 追踪复采任务(如 action=53)已执行的次数，用于在达到最后一次时定性告警并下发 FFT
REDIS_KEY_TASK_SEQ = "task:seq:{task_id}"

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

# 按传感器 SN 缓存的完整诊断上下文，绑定关系变化时必须同步清理。
REDIS_KEY_DIA_DIAGNOSIS_CONTEXT = "dia:diagnosis_context:{sn}"

# 设备健康状态缓存 Key
# 格式: Hash 结构, 键为 dia:health:status, field 为 device_id, value 为 overall_level
# 过期时间: 永久 (由诊断流程实时更新)
# 作用: 提供给 Dashboard 快速查询当前所有设备的健康状态，避免在接口中查询全量最新诊断记录
REDIS_KEY_DIA_HEALTH_STATUS = "dia:health:status"

# 延迟补传诊断状态，每台设备一份；补传完成或新周期开始时删除/替换，最长保留24小时。
REDIS_KEY_DIA_BURST_STATE = "dia:burst:state:{device_id}"

# 已完成诊断的报告幂等标记，防止 Redis Stream 重投造成重复诊断；保留30天。
REDIS_KEY_DIA_DIAGNOSED_REPORT = "dia:diagnosed:report:{report_id}"

# 设备健康档案中的测点趋势短缓存，避免切换温度/振动 TAB 时重复读取 InfluxDB。
# 数据为同一设备、测点、范围和显示窗口的完整趋势响应，60 秒过期。
REDIS_KEY_DEVICE_POINT_TREND = (
    "dia:trend:v1:{tenant_id}:{device_id}:{location_id}:{range_days}:{window_minutes}"
)

# Dashboard 健康快照。
# - snapshot: 每个租户一份完整 Dashboard JSON，避免页面打开时重复执行多表聚合。
# - dirty: Hash，field 为 tenant_id，value 为最近一次诊断写入时间戳（毫秒）。
#   诊断写入只标记快照过期，不删除旧快照；页面可以先返回旧数据，再在后台刷新。
REDIS_KEY_DASHBOARD_HEALTH_SNAPSHOT = "dashboard:health:v1:snapshot:{tenant_id}"
REDIS_KEY_DASHBOARD_HEALTH_DIRTY = "dashboard:health:v1:dirty"
REDIS_KEY_DASHBOARD_HEALTH_REFRESH_LOCK = "dashboard:health:v1:refresh:{tenant_id}"

# ==========================================
# 任务流 (Data Pipelines)
# ==========================================

# 持久化入库任务 Stream Key (api -> persistence)
# 存储内容: { "bucket": str, "path": str }
REDIS_STREAM_PERSISTENCE_INGEST = "stream:persistence:ingest"
REDIS_STREAM_PERSISTENCE_GROUP = "persistence:workers"

# Persistence 报告级并发锁与完成标记。
# processing 最长保留5分钟；processed 保留30天，避免重复持久化和重复触发诊断。
REDIS_KEY_PERSISTENCE_PROCESSING_REPORT = "persistence:processing:{report_id}"
REDIS_KEY_PERSISTENCE_PROCESSED_REPORT = "persistence:processed:{report_id}"

# 诊断触发任务 Stream Key (persistence -> diagnosis)
# 存储内容: { "bucket": str, "path": str }
REDIS_STREAM_DIAGNOSIS_TRIGGER = "stream:diagnosis:trigger"
REDIS_STREAM_DIAGNOSIS_GROUP = "diagnosis:workers"
REDIS_STREAM_FFT_TRIGGER = "stream:diagnosis:fft"
REDIS_STREAM_FFT_GROUP = "diagnosis:fft:workers"
