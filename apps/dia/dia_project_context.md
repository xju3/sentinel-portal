# Dia Service 项目简介

`dia` (Data Ingestion & Analysis) 服务是平台的数据接入与底层分析引擎。它主要负责接收来自底层物联网设备（传感器/网关）的实时遥测数据，完成高效的数据持久化，并在数据入库后触发设备的健康状态诊断与故障分析。

## 核心技术选型与架构
- **开发语言**: Python
- **持久化层 (双库架构)**: 
  - **InfluxDB (时序数据库)**: 存储高频的时序遥测数据（如连续的温度、湿度、振动波形特征等）。
  - **MySQL (关系型数据库)**: 存储分析结果、诊断记录以及更新设备/测点的实时状态（与 `pub` 服务共用底层 SQLAlchemy 数据模型）。
- **数据访问层**: 依赖并共用 `pub` 模块中定义的数据库实体映射（如 `sensor.py`、`device.py` 等）。

## 核心业务工作流 (Workflow)

### 1. 数据接收与解析 (Data Ingestion)
- 监听并接收从设备端上报的有效载荷（通常通过 MQTT/Kafka 等消息中间件）。
- 将原始 payload 解析为标准化的测点指标（温度、湿度、三轴振动、电量等）。

### 2. 双重持久化存储 (Data Persistence)
- **写入 InfluxDB**: 将解析后的时间序列遥测数据快速打点写入时序库，利用 tag 记录 `sensor_id`、`device_inst_id` 和 `tenant_id`，利用 field 记录具体数值。
- **写入 MySQL**: 将瞬时状态快照（如 `SensorStatus`）更新到关系型数据库中，保证业务平台随时可查询最新状态。

### 3. 故障诊断与分析 (Diagnostic Analysis)
- **规则匹配**: 读取 `pub` 库中的 `SensorThreshold`（传感器告警阈值规则），根据短时/中时斜率 (st/mt slope)、幅值 (amplitude) 以及基线 (baseline) 参数，评估刚刚接收到的数据。
- **异常判定**: 结合 `DeviceCategory` 上的默认阈值或租户自定义规则，分析是否存在振动或温度异常。
- **状态与结果回写**:
  - 若发现异常，更新 `SensorMonitoring` 拓扑关联表中的 `anomaly` 状态字段（例如：0=正常, 1=震动异常, 2=温度异常, 3=震动与温度异常），并更新 `ts` 时间戳。
  - 将诊断结论生成健康诊断日志，并插入到 `PatrolDiagnosticRecord` 表中，供前端（如日历热力图）和用户查看具体诊断详情及结论。

## 与 Pub 服务的共用上下文 (Shared Context)

`dia` 服务在操作 MySQL 时，**严格共用** `pub` 服务提供的数据模型上下文，依赖以下关键实体：

1. **`SensorMonitoring`**: 
   - **用途**: 拓扑关系定位与状态更新。
   - **操作**: 接收到数据后，`dia` 依据 `sensor_id` 找到对应的 `device_inst_id`，并在分析完成后更新此表的 `anomaly` 字段。

2. **`SensorThreshold` & `DeviceCategory`**: 
   - **用途**: 诊断规则引擎的参数来源。
   - **操作**: `dia` 通过查询这些表来动态获取某类设备或某个测点在当前租户下的报警阈值上限。

3. **`SensorStatus`**:
   - **用途**: 遥测数据快照。
   - **操作**: `dia` 将最新温湿度、电量更新至此，以便业务后台展示。

4. **`PatrolDiagnosticRecord`**:
   - **用途**: 分析结果持久化。
   - **操作**: 每次定时或触发式的诊断分析完成后，`dia` 会将异常的详细信息（JSON格式）、级别、时间戳持久化到该表。