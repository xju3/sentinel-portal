-- ============================================================
-- 视图: v_device_hierarchy
-- 描述: 合并 DeviceInst, DeviceSpec, DeviceCategory 数据，
--       按设备分类层级统计设备数量，并关联异常信息
-- 输出字段:
--   instance_id        - 设备实例ID
--   spec_id            - 设备规格ID
--   category_id        - 设备分类ID
--   cnt                - 该分类层级下的设备总数（含子分类）
--   parent_category_id - 父分类ID
--   instance_name      - 设备实例名称（code + sn）
--   anomaly            - 异常类型（0=正常, 1=震动异常, 2=温度异常, 3=震动与温度异常）
-- ============================================================

CREATE OR REPLACE VIEW v_device_hierarchy AS
WITH RECURSIVE category_tree AS (
    -- 基础情况：顶级分类
    SELECT dc.id, dc.id AS root_category_id, dc.parent_id, dc.name, 0 AS level
    FROM device_category dc
    WHERE dc.parent_id IS NULL
    UNION ALL
    -- 递归：子分类
    SELECT dc.id, ct.root_category_id, dc.parent_id, dc.name, ct.level + 1
    FROM device_category dc
    INNER JOIN category_tree ct ON dc.parent_id = ct.id
),
-- 统计每个分类下的直接设备数量
device_count_by_category AS (
    SELECT dspec.device_category_id, COUNT(dinst.id) AS direct_cnt
    FROM device_inst dinst
    INNER JOIN device_spec dspec ON dinst.device_spec_id = dspec.id
    GROUP BY dspec.device_category_id
),
-- 统计每个分类层级下的总设备数量（含子分类）
category_device_count AS (
    SELECT ct.id AS category_id, ct.root_category_id, ct.parent_id, ct.name,
           COALESCE(SUM(dc.direct_cnt), 0) AS total_cnt
    FROM category_tree ct
    LEFT JOIN device_count_by_category dc ON dc.device_category_id = ct.id
    GROUP BY ct.id, ct.root_category_id, ct.parent_id, ct.name
)
SELECT dinst.id AS instance_id,
       dspec.id AS spec_id,
       dspec.device_category_id AS category_id,
       COALESCE(cdc.total_cnt, 0) AS cnt,
       dc.parent_id AS parent_category_id,
       CONCAT(dinst.code, ' - ', dinst.sn) AS instance_name,
       COALESCE(sm.anomaly, 0) AS anomaly
FROM device_inst dinst
INNER JOIN device_spec dspec ON dinst.device_spec_id = dspec.id
INNER JOIN device_category dc ON dspec.device_category_id = dc.id
LEFT JOIN category_device_count cdc ON cdc.category_id = dc.id
LEFT JOIN (
    SELECT sm_inner.device_inst_id, MAX(sm_inner.anomaly) AS anomaly
    FROM sensor_monitoring sm_inner
    GROUP BY sm_inner.device_inst_id
) sm ON sm.device_inst_id = dinst.id
ORDER BY dc.parent_id, dc.name, dinst.code;


-- ============================================================
-- 视图: v_device_category_summary
-- 描述: 按设备分类层级汇总统计，展示每个分类的设备总数和异常数
-- ============================================================

CREATE OR REPLACE VIEW v_device_category_summary AS
WITH RECURSIVE category_tree AS (
    -- 基础情况：顶级分类
    SELECT dc.id, dc.id AS root_category_id, dc.parent_id, dc.name, 0 AS level
    FROM device_category dc
    WHERE dc.parent_id IS NULL
    UNION ALL
    -- 递归：子分类
    SELECT dc.id, ct.root_category_id, dc.parent_id, dc.name, ct.level + 1
    FROM device_category dc
    INNER JOIN category_tree ct ON dc.parent_id = ct.id
),
-- 每个分类的直接设备及异常信息
device_with_anomaly AS (
    SELECT dspec.device_category_id, dinst.id AS instance_id,
           COALESCE(sm.anomaly, 0) AS anomaly
    FROM device_inst dinst
    INNER JOIN device_spec dspec ON dinst.device_spec_id = dspec.id
    LEFT JOIN (
        SELECT device_inst_id, MAX(anomaly) AS anomaly
        FROM sensor_monitoring
        GROUP BY device_inst_id
    ) sm ON sm.device_inst_id = dinst.id
),
-- 按分类统计
category_stats AS (
    SELECT device_category_id, COUNT(*) AS total_devices,
           SUM(CASE WHEN anomaly > 0 THEN 1 ELSE 0 END) AS anomaly_devices
    FROM device_with_anomaly
    GROUP BY device_category_id
)
SELECT ct.id AS category_id, ct.root_category_id, ct.parent_id, ct.name, ct.level,
       COALESCE(cs.total_devices, 0) AS total_devices,
       COALESCE(cs.anomaly_devices, 0) AS anomaly_devices
FROM category_tree ct
LEFT JOIN category_stats cs ON cs.device_category_id = ct.id
ORDER BY ct.root_category_id, ct.level, ct.name;
