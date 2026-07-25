# 振动诊断系统架构策略 (Vibration Diagnosis Strategy)

本文档定义了系统中振动（Vibration）特性的诊断降噪逻辑、自动复采状态机、告警冷却机制以及频域（FFT）分析管道。

## 1. 核心评判基准：Vibration Budget Ratio
与温度诊断类似，振动等级不完全依赖硬编码的物理阈值，而是基于**振动载荷占比 (Vibration Budget Ratio)** 进行动态定级。
此处引入了设备在健康正常状态下运行的振动中位数 (`healthy_median`) 作为动态起点。
* **计算公式**：`Ratio = (当前幅值 - 健康中位数) / (危险红线 baseline - 健康中位数)`
* **定级标准**：
  * `< 10%`: Normal / Info
  * `10% ~ 20%`: Attention (关注)
  * `20% ~ 40%`: Abnormal (异常)
  * `40% ~ 70%`: Warning (警告)
  * `>= 70%` (或绝对值超过 baseline): Critical (危险)

---

## 2. 诊断维度与告警拦截 (Diagnosis Dimensions)

为了在低功耗前提下实现精准排障，我们将诊断分为四大维度，并对其赋予不同的**“复采确认 (Re-sampling)”**要求：

### 2.1 必须复采以排除瞬态毛刺的场景
1. **绝对红线 (Absolute Baseline)**：振动幅值接近或突破危险阈值。
2. **实时突变 (Real-Time Mutation)**：当前幅值与上一次幅值的差值，突破了预设的阶跃允许范围 (`rt_max_delta`)，极有可能是传感器受到偶发撞击。
3. **横向同组偏离 (Peer Deviation)**：设备振动大幅度偏离同型号、同工况对等组的振动中位数（如偏离超过 5 mm/s）。

### 2.2 统计学确诊，无需复采的场景
4. **长短期趋势 (Short/Middle-Term Trend)**：
   * 基于过去 24 小时 (Short-Term) 或 72 小时 (Middle-Term) 提取的**拟合斜率 (Slope)** 和**极差振幅 (Amplitude)**。
   * 此类超标是由几十上百个点统计得出的慢性劣化（如轴承缓慢磨损），统计学上已自动平滑了毛刺，因此**直接确诊，直接告警，直接下发 FFT 任务**。

---

## 3. 告警生命周期与 Diagnosis 状态机设计

传统的 0~4 级（Info, Attention, Abnormal, Warning, Critical）无法精确表达设备处于“疑似”和“复核”中的暂态。为此，针对振动诊断扩展了以下专属状态流转码，并硬性写入 `Diagnosis` 数据库表：

### 3.1 传感器指令协议定义
* **特征复采任务**：`action = 53` (固定为 5 分钟 1 次，共采集 3 次)。
* **FFT 拉取任务**：`action = 9xx` (如 902, 904, 908, 916 代表不同量程)。由云端直接下发，点数由传感器根据转速自动决定，无削顶重试。

### 3.2 诊断等级状态机与独立 FFT 表
底层 `Diagnosis` 结构严格保持 `0~4` 级严重度设计。为了区分“确定性告警”与“复核中告警”，在 `Diagnosis` 模型中引入 `resampling` (Boolean) 字段，并辅以独立 `diagnosis_fft` 表应对算法推断：

1. **初次触发 (Level 0~4, resampling=True)**：
   * 发现异常，根据超标幅度计算出 `0~4` 严重度并写入，同时标记 `resampling = True`，代表告警处于“未确诊”状态，拦截向前端/用户的推送。
   * 下发 `action=53` 复采任务，并在 Redis 中生成序数键 `task:seq:{task_id} = 1`。
2. **复核追踪 (前 2 次, resampling=True)**：
   * 接收带 `task_id` 的 53 数据，查 Redis 计数（为 1 或 2）。
   * 继续计算 `0~4` 严重度并写入，保持 `resampling = True`，Redis 计数器 +1。
3. **最终确诊 (第 3 次, resampling=False)**：
   * 查 Redis 发觉已达 3 次。系统计算最终的 `0~4` 危险度并写入，标记 **`resampling = False`**。
   * 此记录代表正式确诊，系统放行对外推送，并下发 `action=9xx` 进行 FFT 采集。
4. **独立 FFT 诊断归档 (`diagnosis_fft`)**：
   * 频谱分析带有探索性和不确定性。结论不覆盖原始的 `0~4` 告警，而是写入独立的 `diagnosis_fft` 表。
   * **置信度抗衡**：该表引入 `confidence` (置信度，0.0~1.0) 字段。通过置信度，系统安全地表达“疑似不平衡”或“特征微弱无法判定”，提供专家参考，避免误导。

### 3.3 24 小时冷却机制 (24h Cooldown / Mute)
为防止设备处于长期故障状态时，系统陷入“疯狂复采与无限拉取 FFT”的死循环（导致电量枯竭与告警风暴）：
* 一旦异常被**确诊 (Confirmed)** 或**趋势劣化报警**，系统会在 Redis 写入 TTL 为 24 小时的静默标记。
* 在此 24 小时内，后续周期采集的异常数据**照常落库**（保证诊断历史连续性），但**强行拦截**所有的复采任务 (`330`)、FFT任务 (`00`) 以及对外推送。
* 24 小时后 TTL 过期，若异常依旧，系统将重新执行一次完整的“复采->FFT->推送”循环（即每日提醒一次）。

---

## 4. FFT 频域诊断触发与双轨分析管道

FFT 频谱分析由于消耗极大带宽和算力，仅在以下三种时机触发：
1. 异常复采被**确诊 (Confirmed)** 时。
2. 趋势斜率/振幅**劣化 (Trend Violation)** 时。
3. 系统**定期健康巡检** (Scheduled Baseline) 时（建立频域指纹）。

### 4.1 硬件边缘侧的量程自适应 (Auto-Ranging)
传感器在采集前具备削顶自检机制。它会自动调整最佳的 FSR (Full-Scale Range, `range_g`) 确保波形无量化噪声且不畸变。
**云端下发策略**：云端直接读取引发本次异常的 Payload 中的 `range_g`，将其直接透传拼接为 FFT 任务指令（例如 `action=0002` 表示 2G FFT，`action=0016` 表示 16G FFT），完全免除云端对于量程的猜测。

### 4.2 云端并行双通道诊断 (Dual-Pipeline Analysis)
为了做到极早期故障的“零漏报”与复合故障的精准定位，**不论底层 `range_g` 是 2G 还是 16G，云端必须同时并行执行以下两大管道**：
## 4. FFT 分析管道与二进制解析

当 `DiagnosisItem` 进入 `status = 20` 并触发 FFT 采集后，设备将上传原始频谱数据。此阶段分为“上传触发”、“文件解析”和“算法双轨诊断”三个环节。

### 4.1 上传闭环与触发机制 (Trigger Pipeline)
1. 传感器上传的 FFT 二进制文件，其文件名即为最初下发任务的 `task_id`。
2. 数据经由 `sensors.py` 存入 MinIO `fft` bucket，并生成 `DeviceFftRecord` 元数据记录。
3. **触发分析**：在元数据记录完成后，系统异步唤醒 Diagnosis Engine 的 FFT 解析单元，向其传入 `task_id`。

### 4.2 二进制文件解析 (Binary Structure)
FFT 解析单元根据 `task_id` 从 MinIO 拉取文件，按严格的小端序 (Little-Endian) 结构解包：
* **Header (前 32 Bytes)**：
  * `0~15`: `SN` 字符串（16字节，null截断）。
  * `16~19`: `Timestamp` (uint32 时间戳)。
  * `20~23`: `Points` (uint32 时域点数，例如 8192)。
  * `24~27`: `Fs` (float32 采样率，例如 26667.0)。
  * `28~31`: `Range_G` (uint32 量程，如 8)。
* **Payload (剩余字节)**：
  * 紧跟 $N/2$个 (如 4096) `X 轴频谱幅值 (float32)`。
  * 紧跟 $N/2$个 (如 4096) `Y 轴频谱幅值 (float32)`。
  * 紧跟 $N/2$个 (如 4096) `Z 轴频谱幅值 (float32)`。
  * 合计 12288 个 float32，共计 49152 Bytes。

### 4.3 物理推断与状态终结 (Root-Cause Inference)
系统提取出三轴有效频谱阵列后：
1. **低频管道 (Rotodynamics)**：分析 1X, 2X, 3X 转频倍频分量，排查转子不平衡 (Unbalance)、不对中 (Misalignment)、机械松动。
2. **高频管道 (Envelope)**：执行包络谱匹配，通过轴承特征频率 (BPFI, BPFO, BSF) 排查滚动体与滚道剥落。
3. **终结归档**：算法输出物理故障代码（如 `UB`, `BPFO`）。反查数据库定位对应的 `DiagnosisItem (status=20)`，将其变更为 `status = 21` (分析完毕)，并写入 `fault_code`，完成全链路报警闭环。

---

## 5. 动态健康基准自学习与滚动机制 (Rolling Baseline & Learning Phase)

设备老化是一个自然现象，其振动中位数必然会随着生命周期缓慢抬升。如果采用出厂死板基线，到了中后期将引发大量“伪告警”。
因此，系统采用**动态滚动基线 (Rolling Baseline)**，让 `Vibration Budget Ratio` 公式中的分母（剩余耐受空间）随着设备老化而合理收缩，使系统对异音的敏感度自然提升。

### 5.1 独立基线存储表 (`device_baseline`)
健康基准不可存在全局配置中，必须绑定具体的物理测点，且需要保留演进历史。引入独立的 `device_baseline` 表：
* **核心字段**：
  * `device_inst_id` / `location_id`: 绑定具体测点。
  * `healthy_median`: 当前生效的健康中位数。
  * `effective_from` & `effective_to`: 生效与失效时间戳，形成完整的基线迭代历史轴。
  * `source`: 来源标识（例如 `learning_cron` 表示定时自学习，`manual_override` 表示人工干预）。

### 5.2 滚动自学习生命周期
1. **初装/大修 (Reset & Initial Learning)**：
   新设备上线或大修重置后，系统进入初始“自学习期”（如 7 天）。在此期间产生的数据经由 Cron Job 离线计算出第一代 `healthy_median`，写入 `device_baseline`，此时 `effective_to` 为空（持续生效）。
2. **滚动迭代 (Rolling Update)**：
   系统按周期（如月度）在后台评估稳态中位数。若未发生真报警且抬升符合自然老化规律，系统将生成下一代基线，同时封闭上一代的 `effective_to`。
3. **实时拉取 (Real-time Extraction)**：
   诊断引擎执行时，联合查询 `device_baseline`，永远提取 `effective_to` 为空的最新一代基线，代入 `Ratio` 公式进行敏感度自适应计算。

### 5.3 冷启动期间的自适应策略 (Cold Start Strategy)
在新设备上线初期的 7 天自学习期内，系统面临尚未生成专属基准的“基线真空期”。为防止误报和漏报，系统在此阶段采用以下两项保底策略：
1. **退化为绝对红线 (Fallback to Zero)**：
   提取不到有效基线时，默认 `healthy_median = 0.0`。Ratio 公式 `(当前值 - 0) / (Baseline - 0)` 退化为纯粹的 `当前值 / Baseline`，此时系统完全依据 ISO 等标准绝对物理阈值进行粗放型保护。
2. **冻结趋势劣化告警 (Trend Alarm Mute)**：
   在处于 `learning_status = 0` 的自学习期间，设备的磨合数据波动较大，系统将强行屏蔽所有长短期趋势劣化告警（Slope / Amplitude），仅保留最核心的“突破绝对红线”和“瞬态突变”检查，待首代基线生成后再全面解封敏感诊断。

---

## 6. 边缘场景与演进考量 (Edge Cases & Future Considerations)

为了确保系统的长期鲁棒性，以下三大工业界常见边缘场景已被纳入战略视野，并形成当前版本的处理共识：

### 6.1 变频与变工况设备 (Variable Speed & Load)
* **当前版本策略**：目前架构主要针对**定频 (Constant Speed)** 设备设计，维持单一的健康基准。
* **业务规避方案**：若现场存在变频设备，需要强依赖管理制度。当设备发生变频切换时，要求用户在管理程序中手动更新设备的转速参数，并主动触发“重置基准”，进入新一轮自学习。
* **未来演进**：后续版本可考虑引入“按转速区间 (RPM Bins)”分别存储多条 `device_baseline`，实现工况自适应。

### 6.2 启停机共振穿越 (Startup & Shutdown Transients)
* **物理现象**：大型设备开/停机通过临界转速时，必然产生剧烈的机械共振，引发数值暴涨。
* **当前版本策略 (天然过滤)**：系统无需额外开发启停机状态识别逻辑。依赖于**“复采状态机”**的时延屏障（发生突变后，执行每 5 分钟 1 次、连续 3 次的特征数据复核），能够完美横跨长达 15 分钟的启停机时间窗。共振引起的瞬态异常在复采结束时必已消失，从而自动归入 `Transient Anomaly`，被完美降噪。

### 6.3 三轴向不对等性 (Axis Anisotropy)
* **物理现象**：大部分卧式设备的水平振动天生大于垂直振动。当前系统取 X, Y, Z 三轴的 `max_rms_vel_mm_s` 作为指标。
* **潜在风险**：虽然取最大值是最安全的底线保护，但若设备的某个刚性极强的轴向（如轴向 Axial）发生微弱的早期劣变，其微小增量可能会被另一个轴向（如水平方向 Horizontal）巨大的底噪掩盖。
* **未来演进**：此问题已记录在案。未来系统将在 `device_baseline` 和诊断引擎中进行维度升维，从 `Max(XYZ)` 拆解为 `X_median`, `Y_median`, `Z_median` 分别追踪，实现轴向级的高精度解耦诊断。
