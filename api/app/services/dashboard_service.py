"""
Dashboard service - business logic for dashboard aggregations
"""

import json
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

        # 4a. 按异常类型分类统计 (anomaly=1 震动异常, anomaly=2 温度异常, anomaly=3 双异常)
        async def _count_by_anomaly(anomaly_value: int) -> int:
            stmt = (
                select(func.count(func.distinct(SensorMonitoring.device_inst_id)))
                .join(DeviceInst, SensorMonitoring.device_inst_id == DeviceInst.id)
                .join(DeviceSpec, DeviceInst.device_spec_id == DeviceSpec.id)
                .join(DeviceCategory, DeviceSpec.device_category_id == DeviceCategory.id)
                .where(
                    DeviceCategory.tenant_id == tenant_id,
                    SensorMonitoring.anomaly == anomaly_value
                )
            )
            return (await session.execute(stmt)).scalar() or 0

        vibration_anomaly_count = await _count_by_anomaly(1)
        temperature_anomaly_count = await _count_by_anomaly(2)
        both_anomaly_count = await _count_by_anomaly(3)

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

        # 6. 按设备分类树聚合设备总数和异常设备数
        devices_by_category_tree = await DashboardService._get_category_device_tree(
            session, tenant_id
        )

        return {
            "totalDevices": total_devices,
            "runningDevices": running_devices,
            "faultyDevices": faulty_devices,
            "newDevicesToday": new_devices_today,
            "vibrationAnomalyCount": vibration_anomaly_count,
            "temperatureAnomalyCount": temperature_anomaly_count,
            "bothAnomalyCount": both_anomaly_count,
            "recentAnomalies": recent_anomalies,
            "devicesByCategoryTree": devices_by_category_tree
        }

    @staticmethod
    async def _get_category_device_tree(
        session: AsyncSession, tenant_id: UUID
    ) -> list:
        """
        按设备分类树聚合设备总数和异常设备数。
        先确定分类树结构，再统计每个分类下的设备总数和异常设备数。
        返回树形结构: [{name, total, anomaly, children: [...]}]
        """
        # 1. 获取该租户下所有 DeviceCategory
        stmt_cats = (
            select(DeviceCategory)
            .where(DeviceCategory.tenant_id == tenant_id)
        )
        cat_rows = (await session.execute(stmt_cats)).scalars().all()

        # 构建分类字典，包含基础统计字段 (统一转为 str 确保查找匹配)
        cat_map = {}
        for cat in cat_rows:
            cat_map[str(cat.id)] = {
                "id": str(cat.id),
                "name": cat.name,
                "parent_id": str(cat.parent_id) if cat.parent_id else None,
                "total": 0,
                "anomaly": 0,
                "children": [],
            }

        # 2. 完全按建议算法：将设备实例、规格、分类、异常测点提取合并为一个平铺组合数据
        stmt_devices = (
            select(
                DeviceInst.id.label("inst_id"),
                DeviceInst.code.label("instance_name"),
                DeviceSpec.id.label("spec_id"),
                DeviceCategory.id.label("category_id"),
                func.max(SensorMonitoring.anomaly).label("anomaly")
            )
            .select_from(DeviceInst)
            .join(DeviceSpec, DeviceInst.device_spec_id == DeviceSpec.id)
            .join(DeviceCategory, DeviceSpec.device_category_id == DeviceCategory.id)
            .outerjoin(SensorMonitoring, SensorMonitoring.device_inst_id == DeviceInst.id)
            .where(DeviceCategory.tenant_id == tenant_id)
            .group_by(DeviceInst.id, DeviceInst.code, DeviceSpec.id, DeviceCategory.id)
        )
        device_rows = (await session.execute(stmt_devices)).all()

        # 3. 对组合数据进行在内存中的精确累加 (从叶子向所有祖级传递)
        for row in device_rows:
            cid = str(row.category_id) if row.category_id else None
            if not cid or cid not in cat_map:
                continue
                
            is_anomaly = 1 if (row.anomaly and row.anomaly > 0) else 0
            
            # 将当前实例的数据累加到自身直接分类，并不断向上追溯累加到全部上级父分类
            curr_cid = cid
            visited = set()
            while curr_cid and curr_cid in cat_map:
                if curr_cid in visited:
                    break  # 防止数据中的死循环环状关联
                visited.add(curr_cid)
                
                cat_map[curr_cid]["total"] += 1
                cat_map[curr_cid]["anomaly"] += is_anomaly
                
                curr_cid = cat_map[curr_cid]["parent_id"]

        # 4. 组装父子树形结构提供给前端
        tree = []
        for cid, info in cat_map.items():
            pid = info["parent_id"]
            if pid and pid in cat_map:
                cat_map[pid]["children"].append(info)
            else:
                # 无父节点的即为最顶层根节点
                tree.append(info)

        print("=== NestedPieChart Tree Data ===")
        print(json.dumps(tree, ensure_ascii=False, indent=2))

        return tree
