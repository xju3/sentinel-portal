DELIMITER $$

DROP PROCEDURE IF EXISTS sp_20260730_add_location_bearing_point $$

CREATE PROCEDURE sp_20260730_add_location_bearing_point()
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'location'
          AND COLUMN_NAME = 'is_bearing_point'
    ) THEN
        ALTER TABLE location
            ADD COLUMN is_bearing_point TINYINT(1) NOT NULL DEFAULT 0
            AFTER description;
    END IF;
END $$

CALL sp_20260730_add_location_bearing_point() $$
DROP PROCEDURE sp_20260730_add_location_bearing_point $$

DELIMITER ;
