# Database Design & Data Model Overview

This document defines the core data models, multi-tenancy rules, and entity relationships within the `pub` service. It serves as essential context for AI assistants to understand the schema structure and domain-driven boundaries.

## 1. Core Principles
- **Multi-Tenancy**: The vast majority of entities include a `tenant_id` to enforce strict data isolation per customer/tenant.
- **Primary Keys**: UUIDs (`id`) are used universally as primary keys, generated via `uuid.uuid4`.
- **Soft Deletes**: Tables typically use an `active` boolean or `status` small integer instead of hard deleting records.

## 2. Module: Customer & Base Config (`customer.py`)
Defines tenant isolation, organization structure, and foundational reference data.
- **`Tenant`**: The root multi-tenant entity. Owns users, locations, and configurations.
- **`TenantSensor`**: Tracks sensor inventory/allocation to a specific tenant.
- **`Account` & `Contact`**: User credentials and contact info, tied to a `Tenant`.
- **`Supplier`**: Hardware/Service suppliers (e.g., for devices), isolated by `Tenant`.
- **`Area` & `Location`**: Spatial management. `Area` supports a hierarchical structure via `parent_id`.
- **`HealthCheckFreq` & `IsoStandard`**: Rules and standards configurations used for system health diagnostics.

## 3. Module: Device Management (`device.py`)
Manages the lifecycle, specification, and hierarchical grouping of physical equipment.
- **`DeviceCategory`**: Hierarchical classification (`parent_id`). Links to default behaviors like `vib_threshold`, `temp_threshold`, `health_check_freq`, and `iso_standard`.
- **`DeviceSpec`**: Defines a hardware model. Belongs to a `DeviceCategory` and a `Supplier`.
- **`DeviceInst`**: A physical instance of a device (asset tracking via `code`/`sn`). Instantiated from a `DeviceSpec`.
- **`Process` / `ProcessItem` / `ProcessDevice` / `ProcessDeviceItem`**: Used to group devices into operational combos, production lines, or specific workflow processes tied to an `Area`.

## 4. Module: Sensor & Monitoring (`sensor.py`)
Tracks sensor hardware, firmware, real-time data, and anomaly states.
- **`SensorType` & `SensorBatch`**: Defines physical capabilities (battery, network) and purchasing batches.
- **`Sensor`**: A physical sensor entity (tracked by `sn`).
- **`SensorFirmware`**: OTA firmware version management.
- **`SensorMonitoring`**: **Core Associative Entity**. Links a `DeviceInst`, a `Sensor`, and a `Location`. It records the installation `direction` and tracks the current `anomaly` status (e.g., vibration/temp anomalies).
- **`SensorStatus`**: Time-series/telemetry snapshot of a sensor (temperature, humidity, vibration, battery).
- **`SensorThreshold`**: Configuration rules defining anomaly thresholds (slopes, amplitudes) for specific metrics.
- **`SensorTask`**: Asynchronous tasks assigned to a specific sensor `sn`.
- **`PatrolDiagnosticRecord`**: System-generated health diagnostic logs/results, tied to sensor `sn`.

## 5. Key Entity Relationships (ER Context)
```text
[ Multi-Tenancy Base ]
Tenant (1) --has-many--> Account, Area, Location, Supplier, Process, SensorBatch

[ Hierarchy Structures ]
Area (1) --has-many--> Area (Self-referencing parent_id)
DeviceCategory (1) --has-many--> DeviceCategory (Self-referencing parent_id)

[ Device Hierarchy ]
DeviceCategory (1) --has-many--> DeviceSpec
Supplier (1)       --has-many--> DeviceSpec
DeviceSpec (1)     --has-many--> DeviceInst

[ Monitoring Topology ]
DeviceInst (1) --has-many--> SensorMonitoring
Sensor (1)     --has-one---> SensorMonitoring  (Sensor is mounted to a DeviceInst)
Location (1)   --has-many--> SensorMonitoring

[ Process/Combo Aggregation ]
Process (1)       --has-many--> ProcessItem (Links to DeviceSpec)
Process (1)       --has-many--> ProcessDevice (Links to Area)
ProcessDevice (1) --has-many--> ProcessDeviceItem (Links to DeviceInst)
```