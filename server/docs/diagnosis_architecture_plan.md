# 重构计划：基于设备维度的新一代诊断模块 (server/diagnosis)

基于您的反馈，我们将彻底重构诊断模块。核心思路是**“以设备 (device_id) 为核心，在报告和结果中区分测点”**，且**“收数存库与诊断工作完全异步解耦”**。我们将在 `server/` 目录下新建一个名为 `diagnosis` 的独立项目。

## 核心业务逻辑共识 (断点续传与异步诊断)

正如您所理解的，由于网络波动导致的离线缓存重传，**数据的接收/入库**与**诊断指令的触发**必须是**异步**且**解耦**的：

1. **数据接收与实时入库 (Ingestion & Storage)**:
   - 接入层收到任何一条数据（无论是实时的还是补发的历史数据），立刻进行解析并**直接存入数据库/时序库**。确保前端看得到最新状态，保证数据不丢失。
2. **诊断触发判定 (Diagnosis Trigger Condition)**:
   - 检查该数据包中的 `delay` 和 `total` 字段。
   - 只有当满足特定条件（即收到 **`total=0`**，代表这一批次所有滞留在硬件里的补发数据已经全部发送完毕），程序才会**发出一条诊断指令（抛入后台诊断队列）**。
3. **时序重排与批量诊断 (Reordering & Sequential Execution)**:
   - 诊断后台 Worker 收到触发指令后，去数据库/缓冲中把这刚刚收集齐的（比如 `n+1` 条）数据全部拉出。
   - **严格按照数据的实际产生时间 (report_ts) 升序排序**。
   - 按时间先后顺序，依次模拟实时推演，进行历史回溯诊断。这样既不会漏诊，也不会因为斜率、趋势计算等依赖时序的算法导致误报。

---

## 重构路线图 (Roadmap)

### 第一阶段 (Step 1)：新建项目与入口/触发器重构 (Project Setup & Ingestion/Trigger) **[本阶段执行重点]**
- **任务**:
  1. 使用 `uv` 初始化 `server/diagnosis` 新项目目录与依赖（复用现有的基础 `pub` 模块）。
  2. 编写接收 Payload 的抽象入口（模拟接收或直接暴露 API）。定义 `DeviceDiagnosticReport` 数据结构模型（以 `device_id` 为核心，包含 `points` 数组）。
  3. **编写触发器中间件**: 实现“只在 `total == 0` 时向诊断消息队列 (Redis Queue) 投递诊断指令”的逻辑。

### 第二阶段 (Step 2)：设备上下文的重构 (Device Context & Topology)
- **任务**:
  1. 重写 `DiagnosisContextService`，以 `device_id` 为入口获取设备的规格、工艺、报警阈值等。
  2. 构建“测点与配置映射”，确保每一个上报的测点数据都能准确匹配到对应的诊断阈值。

### 第三阶段 (Step 3)：诊断引擎 (算法与后台任务) (Diagnostic Engine)

The diagnostic engine is driven by a time-ordered worker (`diagnosis_worker.py`) that processes data strictly by `ts_ms` ascending. 
The algorithms are heavily optimized using a Redis ZSET cache (`TrendCacheService`) that provides memory-speed reads and solves out-of-order backfill issues using `ZREMRANGEBYSCORE` for time-based eviction (e.g., keeping exactly the last 72 hours).

### Temperature Diagnosis: Multi-Tier Trend & Spatial Validation
Based on the principle that absolute temperature is heavily influenced by ambient conditions and thermal resistance, the diagnostic engine completely abandons absolute thresholds in favor of a **Time-Series Multi-Tier + Spatial Validation** model.

#### Phase 1: Temporal Trend Analysis (时间维度多级诊断)
The algorithm evaluates the historical ZSET cache across three distinct time windows:
1. **Real-Time Detection (实时检测)**: 
   - Scans backward from the current point to find continuous monotonic rises. 
   - *Rule*: If temperature rises continuously for $N$ cycles (e.g., 6 periods) AND the total rise exceeds a minimum threshold, flag as `Attention` (关注).
2. **Short-Term Trend (短期检测 - 1天)**: 
   - Calculates the net temperature rise (`Delta-T`) over the past 24 hours.
3. **Mid-Term Trend (中期检测 - 3天)**: 
   - Calculates the net temperature rise (`Delta-T`) over the past 72 hours.

#### Phase 2: Ratio-Based Alarming & Short-Circuit Optimization (比例报警与短路优化)
To maximize computational efficiency and dynamically adjust sensitivity, the algorithm uses a **Ratio-to-Threshold (接近比例)** logic with a brilliant performance optimization:

1. **The 50% Short-Circuit Rule (极速短路优化)**:
   - Calculate `Ratio = current_temp / Absolute_Max_Temp` (e.g., 85°C).
   - **Rule**: If `Ratio < 50%` (e.g., < 42.5°C), the machine is deemed fundamentally safe. The algorithm **instantly exits** with a `Normal` status. It skips all heavy ZSET trend fetches, peer group calculations, and slope analysis. This saves >90% of CPU/Redis overhead for healthy fleets.
   
2. **4-Tier Alerting System (四级报警体系)**:
   If `Ratio >= 50%`, the algorithm fetches the ZSET trends and peer data (Phase 1) to calculate the effective rise, and categorizes the severity based on the absolute ratio:
   - `Ratio > 50%` -> **关注 (Attention)**: Start watching the trend closely.
   - `Ratio > 70%` -> **异常 (Abnormal)**: The margin is shrinking, maintenance should be scheduled.
   - `Ratio > 80%` -> **报警 (Alarm)**: Dangerously hot. Inspection required immediately.
   - `Ratio > 90%` -> **危险 (Danger)**: Imminent failure risk. Shut down recommended.

3. **Trend Override (Noise-Resilient Linear Regression)**: 
   Real-world temperature rises are rarely strictly monotonic due to sensor ADC jitter and air drafts (e.g., 60->62->61->65). To handle this:
   - The algorithm does NOT use naive monotonic checks (`a < b < c`).
   - Instead, it applies **Linear Regression (最小二乘法拟合)** over the time window to calculate the true mathematical **Slope (斜率)**.
   - If the calculated positive slope (Effective Rise) is violently spiking, the status can be artificially escalated (e.g., from 关注 to 报警) to catch sudden catastrophic failures before they hit the 90% threshold.

### Vibration Diagnosis: Multi-Dimensional Fusion Strategy
Vibration is more complex than temperature because a "normal" baseline varies wildly depending on the machine's mounting and balance. The proposed strategy combines **ISO Standards**, **Self-Baseline Deviation**, and **Impulse Features** to create a robust diagnosis for each axis (X, Y, Z).

#### 1. Axis-Independent Evaluation (分轴诊断)
Unlike temperature (a scalar), vibration is a vector. The algorithm runs independently for X (Radial), Y (Radial), and Z (Axial). It outputs separate `DiagnosisItem` records (metric_id = 1, 2, 3) because failure modes differ (e.g., high Z-axis RMS strongly indicates shaft misalignment, while high X/Y indicates unbalance).

#### 2. The 3-Pillar Diagnostic Rules (三大诊断支柱)

**Pillar A: ISO-10816 Absolute Limits (国标绝对值)**
- *Logic*: Retrieve the `IsoStandard` classification from the `DeviceContext` (e.g., Class II, Rigid foundation). 
- *Mapping*: ISO defines strict RMS thresholds for 4 zones (A, B, C, D). These map perfectly to our `Level 0/1, 2, 3, 4`.
- *Use Case*: Prevents catastrophic structural failure.

**Pillar B: Dynamic Baseline Shift (动态基线劣化)**
- *Logic*: Many machines naturally vibrate at 3.0 mm/s (which might be "Abnormal" by strict ISO rules but normal for this specific aged machine). The algorithm establishes a "Baseline RMS" (e.g., average of the first week of healthy operation).
- *Rule*: We calculate `Ratio = Current_RMS / Baseline_RMS`.
  - `Ratio > 1.5` -> Level 1 (Attention)
  - `Ratio > 2.0` -> Level 2 (Abnormal)
  - `Ratio > 3.0` -> Level 3 (Warning)
- *Use Case*: Detects *relative* degradation regardless of how inherently "noisy" the machine is.

**Pillar C: Kurtosis / Crest Factor (峭度早期冲击探测)**
- *Logic*: Early bearing faults (pitting/spalling) generate high-frequency micro-impacts. These impacts are too small to raise the overall RMS energy (Pillar A and B will stay green), but they radically alter the statistical shape of the waveform.
- *Rule*: We examine the `kurtosis` (峭度) feature. A healthy bearing has a kurtosis of ~3.0 (Gaussian).
  - `kurtosis > 4.5` -> Level 2 (Abnormal - Early bearing defect)
  - `kurtosis > 6.0` -> Level 3 (Warning - Severe bearing spalling)
- *Use Case*: Enables predictive maintenance *months* before the RMS rises.

#### 3. Fusion & Final Scoring (融合定级)
The final severity `level` for a specific axis is the `MAX(Pillar_A, Pillar_B, Pillar_C)`.
The `description` and `evidence` JSON will explicitly state which pillar triggered the alarm (e.g., "RMS is normal, but Kurtosis of 5.2 indicates early bearing impact").

## Step 4: Persistence (Data Storage)
The legacy diagnosis tables will be completely refactored to support the new device-centric, integer-encoded architecture.

### Schema Redesign: `diagnosis` (Main Table)
Shifts the anchor from `sensor_sn` to the physical topology (`device_id` + `location_id`).
- `id`: UUID Primary Key
- `device_id`: Link to `DeviceInst` (The machine)
- `location_id`: Link to `Location` (The specific monitoring point)
- `report_id`: Link to the original raw payload in MinIO/MySQL for traceability
- `overall_level`: `Int` (MAX of all item levels, for fast frontend device list querying)
- `diagnosed_at`: `DateTime` (Crucial for time-series partitioning and historic charts)

### Schema Redesign: `diagnosis_item` (Child Table)
Stores the specific result for each metric. Uses ultra-fast integer encoding.
- `id`: UUID Primary Key
- `diagnosis_id`: Foreign Key to `diagnosis`
- `metric_id`: `Int` enum (0: Temperature, 1: Vib-X, 2: Vib-Y, 3: Vib-Z)
- `level`: `Int` encoding of the 4-tier alert system
  - `0`: 正常 (Normal)
  - `1`: 关注 (Attention)
  - `2`: 异常 (Abnormal)
  - `3`: 报警 (Warning)
  - `4`: 危险 (Critical)
- `description`: `String` (Human-readable fault description)
- `evidence`: `JSON` (Optional. Stores algorithm internals like `ratio`, `effective_rise`, `slope` for UI tooltips and debugging)
