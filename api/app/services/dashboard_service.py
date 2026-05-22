"""
Dashboard service - business logic for dashboard aggregations
"""

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date
from uuid import UUID

from app.models.device import DeviceInst, DeviceSpec, DeviceCategory
from app.models.sensor import SensorMonitoring


class DashboardService:
    """Service for handling dashboard data aggregations."""

    @staticmethod
    async def get_overview(session: AsyncSession, tenant_id: UUID) -> dict:
        # 1. 设备总数
        stmt_total = (
            select(func.count(DeviceInst.id))
            .join(DeviceSpec, DeviceInst.device_spec_id == DeviceSpec.id)
            .join(DeviceCategory, DeviceSpec.device_category_id == DeviceCategory.id)
            .where(DeviceCategory.tenant_id == tenant_id)
        )
        total_devices = (await session.execute(stmt_total)).scalar() or 0

        # 2. 运行设备 (active == 1)
        stmt_running = stmt_total.where(DeviceInst.active == 1)
        running_devices = (await session.execute(stmt_running)).scalar() or 0

        # 3. 今日新增 (取 purchase_date 等于今天的数量)
        stmt_new = stmt_total.where(DeviceInst.purchase_date == date.today())
        new_devices_today = (await session.execute(stmt_new)).scalar() or 0

        # 4. 故障设备数 (对应有关联传感器且 anomaly > 0 的不重复设备数)
        stmt_faulty = (
            select(func.count(func.distinct(SensorMonitoring.device_inst_id)))
            .join(DeviceInst, SensorMonitoring.device_inst_id == DeviceInst.id)
            .join(DeviceSpec, DeviceInst.device_spec_id == DeviceSpec.id)
            .join(DeviceCategory, DeviceSpec.device_category_id == DeviceCategory.id)
            .where(
                DeviceCategory.tenant_id == tenant_id,
                SensorMonitoring.anomaly > 0
            )
        )
        faulty_devices = (await session.execute(stmt_faulty)).scalar() or 0

        # 5. 最新故障预警 (获取存在异常的设备及相关信息，按时间倒序)
        stmt_recent = (
            select(
                SensorMonitoring.id,
                DeviceInst.code.label("device_code"),
                DeviceInst.sn.label("device_sn"),
                SensorMonitoring.anomaly,
                SensorMonitoring.ts
            )
            .join(DeviceInst, SensorMonitoring.device_inst_id == DeviceInst.id)
            .join(DeviceSpec, DeviceInst.device_spec_id == DeviceSpec.id)
            .join(DeviceCategory, DeviceSpec.device_category_id == DeviceCategory.id)
            .where(
                DeviceCategory.tenant_id == tenant_id,
                SensorMonitoring.anomaly > 0
            )
            .order_by(SensorMonitoring.ts.desc())
            .limit(10)
        )
        recent_result = await session.execute(stmt_recent)
        recent_anomalies = [
            {
                "id": str(row.id),
                "device_code": row.device_code,
                "device_sn": row.device_sn,
                "anomaly": row.anomaly,
                "ts": row.ts or 0
            } for row in recent_result.all()
        ]

        return {
            "totalDevices": total_devices,
            "runningDevices": running_devices,
            "faultyDevices": faulty_devices,
            "newDevicesToday": new_devices_today,
            "recentAnomalies": recent_anomalies
        }
