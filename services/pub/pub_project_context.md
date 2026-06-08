# Pub Service 项目简介

`pub` 服务是平台的核心公共业务服务，主要负责提供多租户隔离架构、设备资产的全生命周期管理、传感器的状态跟踪以及核心监控拓扑结构（设备-测点-传感器）的维护。

## 核心技术选型
- **开发语言**: Python
- **ORM 框架**: SQLAlchemy
- **数据库**: 关系型数据库 (MySQL)
- **主键策略**: 全表统一使用 UUID (`uuid.uuid4`)
- **删除策略**: 默认采用软删除，通过 `active` (Boolean) 或 `status` (SmallInteger) 字段控制。
- **数据隔离**: 基于 `tenant_id` 的强多租户数据隔离机制，确保跨租户数据绝对安全。

## 核心业务领域 (Domains)

### 1. 租户与基础结构层 (Customer Domain)
- **Tenant (租户)**: 系统的根节点资源，拥有独立的 MQTT 与 API 端点。拥有下属的账号、空间、供应商及规则配置。
- **Account / Contact**: 处理用户身份凭证（邮箱/手机）及联系方式，绑定特定租户。
- **Area / Location**: 物理与逻辑空间映射。其中 `Area` 支持树状层级表示 (`parent_id`)。
- **Rules & Standards**: `HealthCheckFreq`（巡检频率配置）与 `IsoStandard`（ISO10816 / ISO20816 振动标准参考）。

### 2. 设备资产与工艺流程层 (Device Domain)
- **DeviceCategory (设备分类)**: 树状设备分类目录。分类上绑定了默认的振动/温度报警阈值（Threshold）和健康诊断频率。
- **DeviceSpec (设备规格)**: 定义一种硬件型号及其基本参数（如转速 RPM、电压等），隶属于特定供应商和分类。
- **DeviceInst (物理设备实例)**: 具体的资产实体，拥有独立的机器编码（code/sn），记录了采购与生命周期状态。
- **Process / ProcessDevice (工艺与设备组合)**: 用于将多个设备实例打包到一个生产流程或产线中，实现基于产线的聚合监控。

### 3. 传感器与健康监控层 (Sensor Domain)
- **Sensor / SensorType / Batch**: 传感器的物理实体追踪、能力定义（网络、电池特性）及采购批次管理。
- **SensorFirmware**: 用于传感器硬件的 OTA 固件版本管理。
- **SensorMonitoring (核心拓扑桥梁)**: 核心业务关联表。它代表一个“监控测点”，将 `DeviceInst`（被监控的设备）、`Sensor`（负责监控的传感器）以及 `Location` 绑定在一起。记录了传感器的安装方向 (`direction`) 和当前的异常状态 (`anomaly`)。
- **SensorStatus**: 传感器的遥测状态快照（温度、湿度、振动、电量）。
- **SensorThreshold**: 告警阈值配置（短期/中期斜率、幅值限制、基线等）。
- **PatrolDiagnosticRecord**: 系统定期执行诊断任务后生成的健康结论日志。

## 核心实体关系 (ER 链路)

1. **树状层级链路**
   `Area` 和 `DeviceCategory` 分别支持无限级递归的父子层级结构 (`parent_id`)。
   
2. **设备型号派生链路**
   `DeviceCategory` -> `DeviceSpec` -> `DeviceInst`

3. **物理监控拓扑链路**
   一台设备可以拥有多个测点，每个测点挂载一个物理传感器：
   `DeviceInst` (1) ---> (N) `SensorMonitoring` (1) ---> (1) `Sensor`

4. **产线组合链路**
   一个工艺产线由多个工序设备组成，落位在具体区域内：
   `Process` -> `ProcessDevice` (落位于 `Area`) -> `ProcessDeviceItem` (关联具体 `DeviceInst`)