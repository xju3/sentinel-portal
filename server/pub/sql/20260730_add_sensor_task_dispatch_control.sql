DELIMITER $$

DROP PROCEDURE IF EXISTS sp_20260730_add_sensor_task_dispatch_control $$

CREATE PROCEDURE sp_20260730_add_sensor_task_dispatch_control()
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'sensor_task'
          AND column_name = 'dedupe_key'
    ) THEN
        ALTER TABLE sensor_task
            ADD COLUMN dedupe_key VARCHAR(64) NULL
                COMMENT 'Active automatic task idempotency key; cleared on completion'
                AFTER task_purpose;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name = 'sensor_task'
          AND index_name = 'uq_sensor_task_dedupe_key'
    ) THEN
        ALTER TABLE sensor_task
            ADD UNIQUE KEY uq_sensor_task_dedupe_key (dedupe_key);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'sensor_task'
          AND column_name = 'followup_fft_task_id'
    ) THEN
        ALTER TABLE sensor_task
            ADD COLUMN followup_fft_task_id CHAR(32) NULL
                COMMENT 'FFT task selected after this resampling task completed'
                AFTER dedupe_key,
            ADD KEY idx_sensor_task_followup_fft_task_id (followup_fft_task_id),
            ADD CONSTRAINT fk_sensor_task_followup_fft_task
                FOREIGN KEY (followup_fft_task_id) REFERENCES sensor_task (id);
    END IF;
END $$

CALL sp_20260730_add_sensor_task_dispatch_control() $$
DROP PROCEDURE IF EXISTS sp_20260730_add_sensor_task_dispatch_control $$

DELIMITER ;
