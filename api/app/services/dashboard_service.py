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

        # 构建分类映射: id -> {id, name, parent_id, children_ids}
        cat_map = {}
        for cat in cat_rows:
            cat_map[cat.id] = {
                "id": cat.id,
                "name": cat.name,
                "parent_id": cat.parent_id,
                "children_ids": [],
            }
        # 填充 children_ids
        root_ids = []
        for cat_id, info in cat_map.items():
            pid = info["parent_id"]
            if pid and pid in cat_map:
                cat_map[pid]["children_ids"].append(cat_id)
            else:
                root_ids.append(cat_id)

        # 2. 统计每个分类下的设备总数
        stmt_total = (
            select(
                DeviceCategory.id.label("category_id"),
                func.count(DeviceInst.id).label("cnt")
            )
            .select_from(DeviceCategory)
            .outerjoin(DeviceSpec, DeviceSpec.device_category_id == DeviceCategory.id)
            .outerjoin(DeviceInst, DeviceInst.device_spec_id == DeviceSpec.id)
            .where(DeviceCategory.tenant_id == tenant_id)
            .group_by(DeviceCategory.id)
        )
        total_rows = (await session.execute(stmt_total)).all()
        total_counts: dict[UUID, int] = {}
        for row in total_rows:
            total_counts[row.category_id] = row.cnt

        # 3. 统计每个分类下 anomaly > 0 的异常设备数
        stmt_anomaly = (
            select(
                DeviceCategory.id.label("category_id"),
                func.count(func.distinct(SensorMonitoring.device_inst_id)).label("cnt")
            )
            .select_from(DeviceCategory)
            .outerjoin(DeviceSpec, DeviceSpec.device_category_id == DeviceCategory.id)
            .outerjoin(DeviceInst, DeviceInst.device_spec_id == DeviceSpec.id)
            .outerjoin(
                SensorMonitoring,
                (SensorMonitoring.device_inst_id == DeviceInst.id) &
                (SensorMonitoring.anomaly > 0)
            )
            .where(DeviceCategory.tenant_id == tenant_id)
            .group_by(DeviceCategory.id)
        )
        anomaly_rows = (await session.execute(stmt_anomaly)).all()
        anomaly_counts: dict[UUID, int] = {}
        for row in anomaly_rows:
            anomaly_counts[row.category_id] = row.cnt

        # 4. 递归构建树，从叶子节点向上汇总
        def _build_subtree(node_id: UUID) -> dict:
            info = cat_map[node_id]
            children = info["children_ids"]
            if not children:
                # 叶子节点：直接取该分类下的统计值
                return {
                    "name": info["name"],
                    "total": total_counts.get(node_id, 0),
                    "anomaly": anomaly_counts.get(node_id, 0),
                }
            # 非叶子节点：递归构建子节点，汇总 total 和 anomaly
            child_nodes = []
            total_sum = 0
            anomaly_sum = 0
            for child_id in children:
                child_node = _build_subtree(child_id)
                child_nodes.append(child_node)
                total_sum += child_node["total"]
                anomaly_sum += child_node["anomaly"]
            # 过滤掉 total 为 0 的子节点
            child_nodes = [c for c in child_nodes if c["total"] > 0]
            return {
                "name": info["name"],
                "total": total_sum,
                "anomaly": anomaly_sum,
                "children": child_nodes if child_nodes else None,
            }

        tree = []
        for rid in root_ids:
            node = _build_subtree(rid)
            if node["total"] > 0:
                tree.append(node)

        return tree

