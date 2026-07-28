-- 设备健康档案：扩展 diagnosis_record
--
-- diagnosis_status:
--   0 = RECEIVED   已接收，尚未完成诊断
--   1 = WAITING    delay=0,total>0，等待延迟报告补传完成
--   2 = DIAGNOSED  已完成诊断，overall_level 必须为 0~4
--   3 = SKIPPED    delay>0 的历史补传报告，本身不参与诊断
--   4 = MISSED     等待未完成，已被下一条 delay=0 报告替换
--
-- overall_level:
--   NULL = 没有形成诊断结论
--   0    = 正常
--   1    = 关注
--   2    = 异常
--   3    = 告警
--   4    = 严重

ALTER TABLE diagnosis_record
    ADD COLUMN diagnosis_status TINYINT UNSIGNED NOT NULL DEFAULT 0
        COMMENT '0=RECEIVED,1=WAITING,2=DIAGNOSED,3=SKIPPED,4=MISSED'
        AFTER total,
    ADD COLUMN overall_level TINYINT UNSIGNED NULL
        COMMENT '诊断等级:0=正常,1=关注,2=异常,3=告警,4=严重;NULL=未形成诊断'
        AFTER diagnosis_status,
    ADD COLUMN diagnosed_at DATETIME(6) NULL
        COMMENT '实际完成诊断的UTC时间'
        AFTER overall_level,
    ADD INDEX idx_diagnosis_record_device_health_time
        (device_id, diagnosis_status, ts_ms),
    ADD INDEX idx_diagnosis_record_tenant_health_time
        (tenant_id, diagnosis_status, ts_ms);
