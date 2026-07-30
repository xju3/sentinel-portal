DELIMITER $$

DROP PROCEDURE IF EXISTS sp_20260730_add_notification_fault_type_and_diagnosis_case $$

CREATE PROCEDURE sp_20260730_add_notification_fault_type_and_diagnosis_case()
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'diagnosis'
          AND column_name = 'report_uuid'
    ) THEN
        ALTER TABLE diagnosis
            ADD COLUMN report_uuid CHAR(32) NULL COMMENT 'DiagnosisRecord UUID FK' AFTER report_id,
            ADD KEY idx_diagnosis_report_uuid (report_uuid);
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'diagnosis_fft'
          AND column_name = 'report_id'
    ) THEN
        ALTER TABLE diagnosis_fft
            DROP COLUMN report_id;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'diagnosis_item'
          AND column_name = 'fault_type'
    ) THEN
        ALTER TABLE diagnosis_item
            ADD COLUMN fault_type VARCHAR(32) NULL COMMENT 'temperature|vibration|legacy_aggregate' AFTER metric_id,
            ADD KEY idx_diagnosis_item_fault_type (fault_type);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'diagnosis_fft'
          AND column_name = 'device_fft_record_id'
    ) THEN
        ALTER TABLE diagnosis_fft
            ADD COLUMN device_fft_record_id CHAR(32) NULL COMMENT 'Device FFT record UUID FK' AFTER fft_task_id,
            ADD COLUMN rpm_snapshot DOUBLE NULL COMMENT 'RPM snapshot used for FFT reasoning' AFTER confidence,
            ADD COLUMN base_frequency_hz DOUBLE NULL COMMENT 'Base frequency derived from rpm_snapshot' AFTER rpm_snapshot,
            ADD COLUMN rpm_source VARCHAR(32) NULL COMMENT 'report|device_spec' AFTER base_frequency_hz,
            ADD COLUMN spectrum_preview_object_key VARCHAR(255) NULL COMMENT 'MinIO preview artifact key' AFTER rpm_source,
            ADD KEY idx_diagnosis_fft_device_fft_record_id (device_fft_record_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'sensor_task'
          AND column_name = 'diagnosis_case_id'
    ) THEN
        ALTER TABLE sensor_task
            ADD COLUMN diagnosis_case_id CHAR(32) NULL COMMENT 'DiagnosisCase UUID FK' AFTER remark,
            ADD COLUMN source_report_id CHAR(32) NULL COMMENT 'Source DiagnosisRecord UUID FK' AFTER diagnosis_case_id,
            ADD COLUMN source_diagnosis_id CHAR(32) NULL COMMENT 'Source Diagnosis UUID FK' AFTER source_report_id,
            ADD COLUMN task_purpose VARCHAR(32) NULL COMMENT 'RESAMPLING|FFT' AFTER source_diagnosis_id,
            ADD KEY idx_sensor_task_diagnosis_case_id (diagnosis_case_id),
            ADD KEY idx_sensor_task_source_report_id (source_report_id),
            ADD KEY idx_sensor_task_source_diagnosis_id (source_diagnosis_id),
            ADD KEY idx_sensor_task_task_purpose (task_purpose);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'sensor_task_report'
          AND column_name = 'report_uuid'
    ) THEN
        ALTER TABLE sensor_task_report
            ADD COLUMN report_uuid CHAR(32) NULL COMMENT 'DiagnosisRecord UUID FK' AFTER report_id,
            ADD KEY idx_sensor_task_report_report_uuid (report_uuid);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'diagnosis_notification_delivery'
          AND column_name = 'diagnosis_item_id'
    ) THEN
        ALTER TABLE diagnosis_notification_delivery
            ADD COLUMN diagnosis_item_id CHAR(32) NULL COMMENT 'DiagnosisItem UUID snapshot' AFTER device_id;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'diagnosis_notification_delivery'
          AND column_name = 'fault_type'
    ) THEN
        ALTER TABLE diagnosis_notification_delivery
            ADD COLUMN fault_type VARCHAR(32) NULL COMMENT 'temperature|vibration|legacy_aggregate' AFTER overall_level;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'diagnosis_notification_delivery'
          AND column_name = 'fault_level'
    ) THEN
        ALTER TABLE diagnosis_notification_delivery
            ADD COLUMN fault_level TINYINT UNSIGNED NULL COMMENT '1=关注,2=异常,3=告警,4=严重' AFTER fault_type;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'diagnosis_notification_delivery'
          AND column_name = 'recipient_wx_user_id'
    ) THEN
        ALTER TABLE diagnosis_notification_delivery
            ADD COLUMN recipient_wx_user_id VARCHAR(255) NULL COMMENT 'Resolved WeChat user id snapshot' AFTER wx_user_id;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'diagnosis_notification_delivery'
          AND column_name = 'attempt_count'
    ) THEN
        ALTER TABLE diagnosis_notification_delivery
            ADD COLUMN attempt_count INT NOT NULL DEFAULT 0 AFTER sent_at,
            ADD COLUMN next_attempt_at DATETIME(6) NULL AFTER attempt_count,
            ADD KEY idx_diagnosis_notification_retry (status, next_attempt_at);
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'diagnosis_notification_delivery'
          AND column_name = 'overall_level'
          AND is_nullable = 'NO'
    ) THEN
        ALTER TABLE diagnosis_notification_delivery
            MODIFY COLUMN overall_level TINYINT UNSIGNED NULL COMMENT 'Legacy aggregate level snapshot';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name = 'diagnosis_notification_delivery'
          AND index_name = 'idx_diagnosis_notification_report_fault'
    ) THEN
        ALTER TABLE diagnosis_notification_delivery
            ADD KEY idx_diagnosis_notification_report_fault (report_id, fault_type);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name = 'diagnosis_notification_delivery'
          AND index_name = 'idx_diagnosis_notification_diagnosis_item'
    ) THEN
        ALTER TABLE diagnosis_notification_delivery
            ADD KEY idx_diagnosis_notification_diagnosis_item (diagnosis_item_id);
    END IF;

    UPDATE diagnosis_item
    SET fault_type = CASE
        WHEN metric_id = 0 THEN 'temperature'
        WHEN metric_id IN (1, 2, 3) THEN 'vibration'
        ELSE 'legacy_aggregate'
    END
    WHERE fault_type IS NULL;

    UPDATE diagnosis d
    JOIN diagnosis_record dr
      ON LOWER(REPLACE(d.report_id, '-', '')) = LOWER(dr.id)
    SET d.report_uuid = dr.id
    WHERE d.report_id IS NOT NULL
      AND d.report_uuid IS NULL;

    UPDATE sensor_task_report str
    JOIN diagnosis_record dr
      ON LOWER(REPLACE(str.report_id, '-', '')) = LOWER(dr.id)
    SET str.report_uuid = dr.id
    WHERE str.report_uuid IS NULL;

    UPDATE diagnosis_notification_delivery
    SET fault_type = COALESCE(fault_type, 'legacy_aggregate'),
        fault_level = COALESCE(fault_level, overall_level),
        recipient_wx_user_id = COALESCE(recipient_wx_user_id, wx_user_id);

    IF EXISTS (
        SELECT 1
        FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name = 'diagnosis_notification_delivery'
          AND index_name = 'uq_diagnosis_notification_delivery_daily'
          AND seq_in_index = 2
          AND column_name = 'overall_level'
    ) THEN
        ALTER TABLE diagnosis_notification_delivery
            DROP INDEX uq_diagnosis_notification_delivery_daily;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name = 'diagnosis_notification_delivery'
          AND index_name = 'uq_diagnosis_notification_delivery_daily'
          AND seq_in_index = 2
          AND column_name = 'fault_type'
    ) THEN
        ALTER TABLE diagnosis_notification_delivery
            ADD UNIQUE KEY uq_diagnosis_notification_delivery_daily (
                device_id,
                fault_type,
                fault_level,
                employee_id,
                notification_date
            );
    END IF;

    CREATE TABLE IF NOT EXISTS diagnosis_case (
        id CHAR(32) NOT NULL COMMENT 'UUID primary key',
        root_report_id CHAR(32) NOT NULL COMMENT 'DiagnosisRecord UUID FK',
        device_id CHAR(32) NOT NULL COMMENT 'DeviceInst UUID snapshot',
        sensor_sn VARCHAR(255) NOT NULL COMMENT 'Sensor SN snapshot',
        fault_type VARCHAR(32) NOT NULL COMMENT 'temperature|vibration',
        confirmation_status VARCHAR(32) NOT NULL DEFAULT 'INITIAL_ABNORMAL'
            COMMENT 'INITIAL_ABNORMAL|RESAMPLING|RESOLVED_NORMAL|CONFIRMED_ABNORMAL',
        resampling_task_id CHAR(32) NULL COMMENT 'SensorTask UUID',
        confirmed_at DATETIME(6) NULL,
        created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
        PRIMARY KEY (id),
        UNIQUE KEY uq_diagnosis_case_root_report_fault_type (root_report_id, fault_type),
        KEY idx_diagnosis_case_device_id (device_id),
        KEY idx_diagnosis_case_sensor_sn (sensor_sn),
        KEY idx_diagnosis_case_resampling_task_id (resampling_task_id),
        KEY idx_diagnosis_case_confirmation_status (confirmation_status, updated_at),
        CONSTRAINT fk_diagnosis_case_root_report
            FOREIGN KEY (root_report_id) REFERENCES diagnosis_record (id),
        CONSTRAINT fk_diagnosis_case_resampling_task
            FOREIGN KEY (resampling_task_id) REFERENCES sensor_task (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

    CREATE TABLE IF NOT EXISTS diagnosis_case_attempt (
        id CHAR(32) NOT NULL COMMENT 'UUID primary key',
        case_id CHAR(32) NOT NULL COMMENT 'DiagnosisCase UUID FK',
        report_id CHAR(32) NOT NULL COMMENT 'DiagnosisRecord UUID FK',
        diagnosis_id CHAR(32) NULL COMMENT 'Diagnosis UUID FK',
        diagnosis_item_id CHAR(32) NULL COMMENT 'DiagnosisItem UUID FK',
        phase VARCHAR(16) NOT NULL COMMENT 'INITIAL|RESAMPLE',
        sequence INT NOT NULL COMMENT 'Attempt order within phase',
        result_status VARCHAR(32) NOT NULL COMMENT 'NORMAL|ABNORMAL|INSUFFICIENT_DATA',
        fault_level TINYINT UNSIGNED NULL COMMENT '0=正常,1=关注,2=异常,3=告警,4=严重',
        description VARCHAR(255) NULL,
        evidence JSON NULL,
        diagnosed_at DATETIME(6) NULL,
        created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        PRIMARY KEY (id),
        UNIQUE KEY uq_diagnosis_case_attempt_case_report (case_id, report_id),
        UNIQUE KEY uq_diagnosis_case_attempt_case_phase_sequence (case_id, phase, sequence),
        KEY idx_diagnosis_case_attempt_report_id (report_id),
        KEY idx_diagnosis_case_attempt_diagnosis_id (diagnosis_id),
        KEY idx_diagnosis_case_attempt_diagnosis_item_id (diagnosis_item_id),
        CONSTRAINT fk_diagnosis_case_attempt_case
            FOREIGN KEY (case_id) REFERENCES diagnosis_case (id) ON DELETE CASCADE,
        CONSTRAINT fk_diagnosis_case_attempt_report
            FOREIGN KEY (report_id) REFERENCES diagnosis_record (id),
        CONSTRAINT fk_diagnosis_case_attempt_diagnosis
            FOREIGN KEY (diagnosis_id) REFERENCES diagnosis (id),
        CONSTRAINT fk_diagnosis_case_attempt_diagnosis_item
            FOREIGN KEY (diagnosis_item_id) REFERENCES diagnosis_item (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

    CREATE TABLE IF NOT EXISTS diagnosis_notification_outbox (
        id CHAR(32) NOT NULL COMMENT 'UUID primary key',
        event_id CHAR(32) NOT NULL COMMENT 'Notification event UUID',
        diagnosis_id CHAR(32) NOT NULL COMMENT 'Diagnosis UUID FK',
        report_id CHAR(32) NOT NULL COMMENT 'DiagnosisRecord UUID FK',
        payload JSON NOT NULL COMMENT 'MQTT event payload snapshot',
        status VARCHAR(16) NOT NULL DEFAULT 'PENDING' COMMENT 'PENDING|PUBLISHED|FAILED',
        attempt_count INT NOT NULL DEFAULT 0,
        next_attempt_at DATETIME(6) NULL,
        created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        published_at DATETIME(6) NULL,
        last_error VARCHAR(1024) NULL,
        PRIMARY KEY (id),
        UNIQUE KEY uq_diagnosis_notification_outbox_event (event_id),
        KEY idx_diagnosis_notification_outbox_diagnosis_id (diagnosis_id),
        KEY idx_diagnosis_notification_outbox_report_id (report_id),
        KEY idx_diagnosis_notification_outbox_status_retry (status, next_attempt_at),
        CONSTRAINT fk_diagnosis_notification_outbox_diagnosis
            FOREIGN KEY (diagnosis_id) REFERENCES diagnosis (id),
        CONSTRAINT fk_diagnosis_notification_outbox_report
            FOREIGN KEY (report_id) REFERENCES diagnosis_record (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.table_constraints
        WHERE table_schema = DATABASE()
          AND table_name = 'diagnosis'
          AND constraint_name = 'fk_diagnosis_report_uuid'
    ) THEN
        ALTER TABLE diagnosis
            ADD CONSTRAINT fk_diagnosis_report_uuid
                FOREIGN KEY (report_uuid) REFERENCES diagnosis_record (id);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.table_constraints
        WHERE table_schema = DATABASE()
          AND table_name = 'diagnosis_fft'
          AND constraint_name = 'fk_diagnosis_fft_device_fft_record'
    ) THEN
        ALTER TABLE diagnosis_fft
            ADD CONSTRAINT fk_diagnosis_fft_device_fft_record
                FOREIGN KEY (device_fft_record_id) REFERENCES device_fft_record (id);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.table_constraints
        WHERE table_schema = DATABASE()
          AND table_name = 'sensor_task'
          AND constraint_name = 'fk_sensor_task_diagnosis_case'
    ) THEN
        ALTER TABLE sensor_task
            ADD CONSTRAINT fk_sensor_task_diagnosis_case
                FOREIGN KEY (diagnosis_case_id) REFERENCES diagnosis_case (id),
            ADD CONSTRAINT fk_sensor_task_source_report
                FOREIGN KEY (source_report_id) REFERENCES diagnosis_record (id),
            ADD CONSTRAINT fk_sensor_task_source_diagnosis
                FOREIGN KEY (source_diagnosis_id) REFERENCES diagnosis (id);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.table_constraints
        WHERE table_schema = DATABASE()
          AND table_name = 'sensor_task_report'
          AND constraint_name = 'fk_sensor_task_report_report_uuid'
    ) THEN
        ALTER TABLE sensor_task_report
            ADD CONSTRAINT fk_sensor_task_report_report_uuid
                FOREIGN KEY (report_uuid) REFERENCES diagnosis_record (id);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.table_constraints
        WHERE table_schema = DATABASE()
          AND table_name = 'diagnosis_notification_delivery'
          AND constraint_name = 'fk_diagnosis_notification_delivery_item'
    ) THEN
        ALTER TABLE diagnosis_notification_delivery
            ADD CONSTRAINT fk_diagnosis_notification_delivery_item
                FOREIGN KEY (diagnosis_item_id) REFERENCES diagnosis_item (id);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name = 'diagnosis_fft'
          AND index_name = 'uq_diagnosis_fft_task_id'
    ) THEN
        ALTER TABLE diagnosis_fft
            ADD UNIQUE KEY uq_diagnosis_fft_task_id (fft_task_id);
    END IF;
END $$

CALL sp_20260730_add_notification_fault_type_and_diagnosis_case() $$

DROP PROCEDURE IF EXISTS sp_20260730_add_notification_fault_type_and_diagnosis_case $$

DELIMITER ;
