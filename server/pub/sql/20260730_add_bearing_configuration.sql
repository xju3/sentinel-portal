DELIMITER $$

DROP PROCEDURE IF EXISTS sp_20260730_add_bearing_configuration $$

CREATE PROCEDURE sp_20260730_add_bearing_configuration()
BEGIN
    CREATE TABLE IF NOT EXISTS bearing_model (
        id CHAR(32) NOT NULL,
        tenant_id CHAR(32) NOT NULL,
        brand VARCHAR(64) NOT NULL,
        model VARCHAR(64) NOT NULL,
        bearing_type VARCHAR(64) NULL,
        rolling_element_count INT NOT NULL,
        rolling_element_diameter_mm DOUBLE NOT NULL,
        pitch_diameter_mm DOUBLE NOT NULL,
        contact_angle_deg DOUBLE NOT NULL DEFAULT 0,
        description VARCHAR(255) NULL,
        active TINYINT(1) NOT NULL DEFAULT 1,
        PRIMARY KEY (id),
        KEY ix_bearing_model_tenant_id (tenant_id),
        UNIQUE KEY uq_bearing_model_tenant_brand_model (tenant_id, brand, model),
        CONSTRAINT chk_bearing_rolling_element_count
            CHECK (rolling_element_count >= 3),
        CONSTRAINT chk_bearing_element_diameter
            CHECK (rolling_element_diameter_mm > 0),
        CONSTRAINT chk_bearing_pitch_diameter
            CHECK (pitch_diameter_mm > rolling_element_diameter_mm),
        CONSTRAINT chk_bearing_contact_angle
            CHECK (contact_angle_deg >= 0 AND contact_angle_deg < 90),
        CONSTRAINT chk_bearing_type
            CHECK (
                bearing_type IS NULL OR bearing_type IN (
                    'DEEP_GROOVE_BALL',
                    'ANGULAR_CONTACT_BALL',
                    'SELF_ALIGNING_BALL',
                    'CYLINDRICAL_ROLLER',
                    'TAPERED_ROLLER',
                    'SPHERICAL_ROLLER',
                    'NEEDLE_ROLLER',
                    'THRUST_BALL',
                    'THRUST_ROLLER',
                    'OTHER'
                )
            )
    );

    CREATE TABLE IF NOT EXISTS device_spec_bearing (
        id CHAR(32) NOT NULL,
        device_spec_id CHAR(32) NOT NULL,
        bearing_id CHAR(32) NOT NULL,
        location_id CHAR(32) NOT NULL,
        shaft_speed_ratio DOUBLE NOT NULL DEFAULT 1,
        enabled TINYINT(1) NOT NULL DEFAULT 1,
        PRIMARY KEY (id),
        KEY ix_device_spec_bearing_device_spec_id (device_spec_id),
        KEY ix_device_spec_bearing_bearing_id (bearing_id),
        KEY ix_device_spec_bearing_location_id (location_id),
        UNIQUE KEY uq_device_spec_bearing_spec_location (device_spec_id, location_id),
        CONSTRAINT fk_device_spec_bearing_device_spec
            FOREIGN KEY (device_spec_id) REFERENCES device_spec (id)
            ON DELETE CASCADE,
        CONSTRAINT fk_device_spec_bearing_bearing
            FOREIGN KEY (bearing_id) REFERENCES bearing_model (id)
            ON DELETE RESTRICT,
        CONSTRAINT fk_device_spec_bearing_location
            FOREIGN KEY (location_id) REFERENCES location (id)
            ON DELETE RESTRICT,
        CONSTRAINT chk_device_spec_bearing_shaft_speed_ratio
            CHECK (shaft_speed_ratio > 0 AND shaft_speed_ratio <= 1000)
    );
END $$

CALL sp_20260730_add_bearing_configuration() $$
DROP PROCEDURE sp_20260730_add_bearing_configuration $$

DELIMITER ;
