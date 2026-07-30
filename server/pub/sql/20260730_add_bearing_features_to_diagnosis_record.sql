-- Preserve the exact per-cycle bearing evidence uploaded by the device.
-- The column is optional so reports from devices without bearing configuration
-- continue through the existing diagnosis path unchanged.

DELIMITER $$

DROP PROCEDURE IF EXISTS sp_20260730_add_bearing_features_to_diagnosis_record $$

CREATE PROCEDURE sp_20260730_add_bearing_features_to_diagnosis_record()
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'diagnosis_record'
          AND COLUMN_NAME = 'bearing_features'
    ) THEN
        ALTER TABLE diagnosis_record
            ADD COLUMN bearing_features JSON NULL
                COMMENT '设备端逐轴轴承包络特征证据'
                AFTER quality;
    END IF;
END $$

CALL sp_20260730_add_bearing_features_to_diagnosis_record() $$
DROP PROCEDURE sp_20260730_add_bearing_features_to_diagnosis_record $$

DELIMITER ;
