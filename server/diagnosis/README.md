# Sentinel Platform - Diagnosis Module

## 模块定位 (Architecture Role)
`diagnosis` 模块是全新重构的边缘设备数据入库与诊断引擎的网关服务。
- 它本身**保持轻量化**，所有的底层数据库管理（`db_manager`, `influxdb_manager`）、ORM 模型（`pub.models`）以及缓存机制都严格依赖于核心的 `server/pub` 模块。
- 它的使命是替代原有老旧且将被废弃的 `dia` 服务，实现更加面向对象、设备粒度的精准诊断。

## 核心数据交互规范 (Data Flow Rules)
新加入的 AI 工程师在介入本模块开发时，必须遵循以下核心认知和约定：

### 1. 报文准入校验 (`payload.py`)
所有的 MQTT 入口数据都必须通过 `DeviceDiagnosticReport` Pydantic 模型的严格校验。
**必须满足 4 大强校验字段**才能被放行（少一个就会报 422 错误）：
- `device_id`: 设备 ID
- `sensor_id`: 传感器 (测量点) ID
- `location_id`: 安装位置 ID
- `ts_ms`: 时间戳（算法时间线计算的唯一真理）

### 2. 双库持久化分离策略 (`ingestion.py`)
在 `process_incoming_report` 方法中，数据被分流到了两套不同的数据库：
- **时序特征（海量） -> InfluxDB**：
  直接将 `temperature_c` 和各轴（X/Y/Z）的 `rms_acc_g` 及计算得出的 `rms_m` 封印进 `vibration_feature` 表中，作为后期的时域、频域画布数据源。
- **状态与诊断结论（精准） -> MySQL**：
  MySQL 只存状态字与“判案结论”。

### 3. 诊断触发器机制 (Triggering Rule)
**绝对不能来一条数据就诊断一次！**
只有当收到的报文带有 **`total == 0`** 标志时（意味着网络延迟或历史积压的所有分包已经全部收齐，当前就是完整的时间切片结尾），才可以触发诊断引擎。
代码实现见 `dispatch_diagnosis_trigger`，它会执行以下串行操作：
1. 调用 `DeviceContextService` 从 MySQL 中反查该设备的最新阈值配置。
2. 将数据送入核心算法（如 `TemperatureDiagnosis.analyze`）。
3. 将返回的结果落盘至 MySQL 的 `diagnosis`（总表）和 `diagnosis_item`（明细表）。

## 环境与测试说明
- **运行环境**：使用 `server/.venv` 中的 Python 执行环境。
- **数据库连接**：需要读取 `server/api/.env`（或根目录 `.env`）来完成数据库初始化，初始化由 FastAPI `lifespan` 完成，或在测试脚本中手动调用。
- **联调测试**：可以通过根目录的 `test_script.py` 对整个 `ingestion.py` 的数据解析、InfluxDB 写入、MySQL 诊断结果生成进行端到端的贯穿测试。
