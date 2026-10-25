DELIMITER $$

DROP PROCEDURE IF EXISTS sp_20261026_add_device_operation_schedule $$

CREATE PROCEDURE sp_20261026_add_device_operation_schedule()
BEGIN
    CREATE TABLE IF NOT EXISTS device_operation_schedule (
        id CHAR(32) NOT NULL,
        tenant_id CHAR(32) NOT NULL,
        code VARCHAR(16) NOT NULL,
        name VARCHAR(64) NOT NULL,
        description VARCHAR(255) NULL,
        status SMALLINT NOT NULL DEFAULT 1 COMMENT '1:启用, 0:停用',
        PRIMARY KEY (id),
        KEY ix_device_operation_schedule_tenant_id (tenant_id),
        UNIQUE KEY uq_op_schedule_tenant_code (tenant_id, code)
    );

    CREATE TABLE IF NOT EXISTS device_operation_schedule_items (
        id CHAR(32) NOT NULL,
        schedule_id CHAR(32) NOT NULL,
        cron_expr VARCHAR(64) NOT NULL COMMENT '启动时刻Crontab表达式',
        duration_minutes INT NOT NULL COMMENT '持续运行时长(分钟)',
        remark VARCHAR(128) NULL COMMENT '时段说明',
        seq INT NOT NULL DEFAULT 0 COMMENT '排序号',
        PRIMARY KEY (id),
        KEY ix_device_operation_schedule_items_schedule_id (schedule_id),
        CONSTRAINT fk_op_schedule_items_schedule
            FOREIGN KEY (schedule_id) REFERENCES device_operation_schedule (id)
            ON DELETE CASCADE
    );

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'device_spec'
          AND COLUMN_NAME = 'speed_mode'
    ) THEN
        ALTER TABLE device_spec
            ADD COLUMN speed_mode SMALLINT NOT NULL DEFAULT 1 COMMENT '1:定速, 2:变频'
            AFTER voltage;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'device_spec'
          AND COLUMN_NAME = 'poles'
    ) THEN
        ALTER TABLE device_spec
            ADD COLUMN poles INT NULL COMMENT '电机极数(如2,4,6,8)'
            AFTER speed_mode;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'device_spec'
          AND COLUMN_NAME = 'frequency_hz'
    ) THEN
        ALTER TABLE device_spec
            ADD COLUMN frequency_hz DOUBLE NULL COMMENT '变频运行频率(Hz)'
            AFTER poles;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'device_spec'
          AND COLUMN_NAME = 'operation_mode'
    ) THEN
        ALTER TABLE device_spec
            ADD COLUMN operation_mode SMALLINT NOT NULL DEFAULT 1 COMMENT '1:连续运行, 2:事件触发, 3:时段运行'
            AFTER remark;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'device_spec'
          AND COLUMN_NAME = 'reference_id'
    ) THEN
        ALTER TABLE device_spec
            ADD COLUMN reference_id CHAR(32) NULL COMMENT '关联运行模式(device_operation_schedule)ID'
            AFTER operation_mode,
            ADD KEY ix_device_spec_reference_id (reference_id),
            ADD CONSTRAINT fk_device_spec_operation_schedule
                FOREIGN KEY (reference_id) REFERENCES device_operation_schedule (id)
                ON DELETE RESTRICT;
    END IF;
END $$

CALL sp_20261026_add_device_operation_schedule() $$
DROP PROCEDURE sp_20261026_add_device_operation_schedule $$

DELIMITER ;
