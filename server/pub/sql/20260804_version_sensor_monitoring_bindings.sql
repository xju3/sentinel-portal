-- 将 sensor_monitoring 改为不可覆盖的绑定历史。
-- status=1 表示当前有效；status=0 表示已经解除的历史绑定。

ALTER TABLE sensor_monitoring
    ADD COLUMN bound_at DATETIME(6) NOT NULL
        DEFAULT CURRENT_TIMESTAMP(6)
        COMMENT '绑定生效时间(UTC)'
        AFTER status,
    ADD COLUMN unbound_at DATETIME(6) NULL
        COMMENT '绑定解除时间(UTC)，NULL表示当前有效'
        AFTER bound_at,
    ADD INDEX idx_sensor_monitoring_sensor_status (sensor_id, status),
    ADD INDEX idx_sensor_monitoring_point_status
        (device_inst_id, location_id, status);

UPDATE sensor_monitoring
SET unbound_at = bound_at
WHERE status <> 1
  AND unbound_at IS NULL;
