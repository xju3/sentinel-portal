-- 设备健康档案按测点查询索引。
-- 多测点设备的健康档案必须按 device_id + location_id 分开统计。

ALTER TABLE diagnosis_record
    ADD INDEX idx_diag_record_device_location_health_time
        (device_id, location_id, ts_ms, diagnosis_status);
