"""
Dashboard Health Service - focused health overview for equipment managers.

Provides a single endpoint that returns three blocks of data:
1. Health summary (device counts by level)
2. Problem distribution (by category and area)
3. Fault device list (prioritized by severity, duration, and trend)
"""

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pub.models.device import DeviceCategory, DeviceInst, DeviceSpec, ProcessDevice, ProcessDeviceItem
from pub.models.diagnosis import DiagnosisResult
from pub.models.customer import Area
from pub.models.sensor import CommunicationState, Sensor, SensorMonitoring

logger = logging.getLogger(__name__)

LEVEL_SCORE = {
    "未检测": -1,
    "正常": 0,
    "关注": 1,
    "警告": 2,
    "严重": 3,
}

METRIC_LABELS = {
    "quality": "数据质量",
    "temperature": "温度",
    "vibration_intensity": "振动强度",
    "energy_impact": "能量冲击",
    "peak_structure": "主频结构",
}

OFFLINE_AFTER_MS = 24 * 60 * 60 * 1000


class DashboardHealthService:
    """Health-focused dashboard: summary → distribution → fault list."""

    @staticmethod
    async def get_health_dashboard(session: AsyncSession, tenant_id: UUID) -> dict:
        # 1. Query all devices with category, area, sns
        devices = await DashboardHealthService._query_devices(session, tenant_id)
        total_devices = len(devices)

        # 2. Collect all monitored SNs
        sn_to_devices: dict[str, list[str]] = {}
        monitored_sns: set[str] = set()
        for dev in devices.values():
            for sn in dev["sns"]:
                monitored_sns.add(sn)
                sn_to_devices.setdefault(sn, []).append(dev["device_id"])

        # 3. Query latest diagnosis results per (sn, metric)
        latest_results = await DashboardHealthService._query_latest_diagnosis(
            session, monitored_sns
        )

        # 4. Query communication states for online/offline
        comm_states = await DashboardHealthService._query_comm_states(
            session, monitored_sns
        )

        # 5. Determine online status per device
        now_ms = int(datetime.utcnow().timestamp() * 1000)
        for sn in monitored_sns:
            comm = comm_states.get(sn)
            is_online = bool(
                comm and comm.last_ts_ms and now_ms - comm.last_ts_ms <= OFFLINE_AFTER_MS
            )
            for device_id in sn_to_devices.get(sn, []):
                if device_id in devices:
                    if is_online:
                        devices[device_id]["online"] = True

        # 6. Assign diagnosis level to each device & collect triggered metrics
        for sn, metric_results in latest_results.items():
            for result in metric_results.values():
                score = LEVEL_SCORE.get(result.level, 0)
                linked_ids = (
                    [str(result.device_inst_id)]
                    if result.device_inst_id
                    else sn_to_devices.get(sn, [])
                )
                for device_id in linked_ids:
                    if device_id not in devices:
                        continue
                    dev = devices[device_id]
                    dev["has_diagnosis"] = True
                    current_score = dev["diagnosis_score"]
                    if current_score is None or score > current_score:
                        dev["diagnosis_score"] = score
                        dev["diagnosis_level"] = result.level

                    if score > 0:
                        label = METRIC_LABELS.get(result.metric, result.metric)
                        current_metric_level = dev["triggered_metrics"].get(label)
                        if not current_metric_level or score > LEVEL_SCORE.get(current_metric_level, 0):
                            dev["triggered_metrics"][label] = result.level

        # 7. Query fault duration for triggered devices
        fault_device_ids = {
            dev["device_id"]
            for dev in devices.values()
            if LEVEL_SCORE.get(dev["diagnosis_level"], 0) > 0
        }
        fault_sns = set()
        for dev_id in fault_device_ids:
            fault_sns.update(devices[dev_id]["sns"])
        first_triggered_map = await DashboardHealthService._query_first_triggered(
            session, fault_sns
        )
        previous_level_map = await DashboardHealthService._query_previous_levels(
            session, fault_sns
        )

        # 8. Assemble response
        return DashboardHealthService._assemble_response(
            devices=devices,
            total_devices=total_devices,
            sn_to_devices=sn_to_devices,
            first_triggered_map=first_triggered_map,
            previous_level_map=previous_level_map,
            now_ms=now_ms,
        )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    @staticmethod
    async def _query_devices(
        session: AsyncSession, tenant_id: UUID
    ) -> dict[str, dict]:
        """Query all devices with category name, area, and sensor SNs."""
        stmt = (
            select(
                DeviceInst.id.label("device_id"),
                DeviceInst.name.label("device_name"),
                DeviceInst.code.label("device_code"),
                DeviceCategory.name.label("category"),
                Sensor.sn.label("sn"),
                Area.name.label("area"),
            )
            .join(DeviceSpec, DeviceInst.device_spec_id == DeviceSpec.id)
            .join(DeviceCategory, DeviceSpec.device_category_id == DeviceCategory.id)
            .outerjoin(
                SensorMonitoring,
                and_(
                    SensorMonitoring.device_inst_id == DeviceInst.id,
                    SensorMonitoring.status == 1,
                ),
            )
            .outerjoin(Sensor, SensorMonitoring.sensor_id == Sensor.id)
            .outerjoin(
                ProcessDeviceItem, ProcessDeviceItem.device_inst_id == DeviceInst.id
            )
            .outerjoin(
                ProcessDevice, ProcessDevice.id == ProcessDeviceItem.process_device_id
            )
            .outerjoin(Area, Area.id == ProcessDevice.area_id)
            .where(DeviceCategory.tenant_id == tenant_id)
        )
        rows = await session.execute(stmt)
        devices: dict[str, dict] = {}
        for row in rows:
            device_id = str(row.device_id)
            if device_id not in devices:
                devices[device_id] = {
                    "device_id": device_id,
                    "device_name": row.device_name,
                    "device_code": row.device_code,
                    "category": row.category or "未分类",
                    "area": row.area or "未分配",
                    "sns": set(),
                    "online": False,
                    "has_diagnosis": False,
                    "diagnosis_score": None,
                    "diagnosis_level": "未检测",
                    "triggered_metrics": {},
                }
            if row.sn:
                devices[device_id]["sns"].add(row.sn)
            if row.area:
                devices[device_id]["area"] = row.area
        return devices

    @staticmethod
    async def _query_latest_diagnosis(
        session: AsyncSession, sns: set[str]
    ) -> dict[str, dict[str, DiagnosisResult]]:
        """Get latest DiagnosisResult per (sn, metric)."""
        if not sns:
            return {}
        ranked = (
            select(
                DiagnosisResult.id.label("id"),
                func.row_number()
                .over(
                    partition_by=(DiagnosisResult.sn, DiagnosisResult.metric),
                    order_by=(
                        desc(DiagnosisResult.report_ts),
                        desc(DiagnosisResult.diagnosed_at),
                    ),
                )
                .label("row_num"),
            )
            .where(DiagnosisResult.sn.in_(list(sns)))
            .subquery()
        )
        stmt = (
            select(DiagnosisResult)
            .join(ranked, DiagnosisResult.id == ranked.c.id)
            .where(ranked.c.row_num == 1)
        )
        rows = (await session.execute(stmt)).scalars().all()
        latest: dict[str, dict[str, DiagnosisResult]] = {}
        for result in rows:
            latest.setdefault(result.sn, {})[result.metric] = result
        return latest

    @staticmethod
    async def _query_comm_states(
        session: AsyncSession, sns: set[str]
    ) -> dict[str, CommunicationState]:
        if not sns:
            return {}
        stmt = select(CommunicationState).where(CommunicationState.sn.in_(list(sns)))
        rows = (await session.execute(stmt)).scalars().all()
        return {s.sn: s for s in rows}

    @staticmethod
    async def _query_first_triggered(
        session: AsyncSession, sns: set[str]
    ) -> dict[str, datetime]:
        """Get earliest triggered diagnosis time per SN (for duration calculation)."""
        if not sns:
            return {}
        stmt = (
            select(
                DiagnosisResult.sn,
                func.min(DiagnosisResult.diagnosed_at).label("first_at"),
            )
            .where(
                DiagnosisResult.sn.in_(list(sns)),
                DiagnosisResult.triggered.is_(True),
            )
            .group_by(DiagnosisResult.sn)
        )
        rows = await session.execute(stmt)
        return {row.sn: row.first_at for row in rows if row.first_at}

    @staticmethod
    async def _query_previous_levels(
        session: AsyncSession, sns: set[str]
    ) -> dict[str, str]:
        """Get the second-latest diagnosis level per SN to determine trend.

        Compare the latest report's max level with the previous report's max level.
        """
        if not sns:
            return {}

        # Get the two most recent distinct report_ts per SN
        ranked = (
            select(
                DiagnosisResult.sn,
                DiagnosisResult.report_ts,
                DiagnosisResult.level,
                func.row_number()
                .over(
                    partition_by=DiagnosisResult.sn,
                    order_by=(
                        desc(DiagnosisResult.report_ts),
                        desc(DiagnosisResult.diagnosed_at),
                    ),
                )
                .label("row_num"),
            )
            .where(DiagnosisResult.sn.in_(list(sns)))
            .subquery()
        )

        # Get all results where row_num corresponds to the 2nd report cycle
        # (i.e., results 6-10 if each cycle has 5 metrics)
        # Simplified: get all non-latest report_ts results and pick the max level
        stmt = (
            select(
                ranked.c.sn,
                ranked.c.level,
            )
            .where(ranked.c.row_num > 5, ranked.c.row_num <= 10)
        )
        rows = await session.execute(stmt)

        # Take the max level per SN from the previous cycle
        prev: dict[str, int] = {}
        for row in rows:
            score = LEVEL_SCORE.get(row.level, 0)
            if row.sn not in prev or score > prev[row.sn]:
                prev[row.sn] = score

        score_to_level = {v: k for k, v in LEVEL_SCORE.items()}
        return {sn: score_to_level.get(s, "未检测") for sn, s in prev.items()}

    # ------------------------------------------------------------------
    # Assemble
    # ------------------------------------------------------------------

    @staticmethod
    def _assemble_response(
        devices: dict[str, dict],
        total_devices: int,
        sn_to_devices: dict[str, list[str]],
        first_triggered_map: dict[str, datetime],
        previous_level_map: dict[str, str],
        now_ms: int,
    ) -> dict[str, Any]:
        # --- Health summary ---
        counts = {"normal": 0, "attention": 0, "warning": 0, "severe": 0, "offline": 0, "unconfigured": 0}
        monitored_count = 0

        for dev in devices.values():
            if not dev["sns"]:
                counts["unconfigured"] += 1
                continue
            monitored_count += 1
            if not dev["online"]:
                counts["offline"] += 1
                continue
            level = dev["diagnosis_level"]
            if level == "严重":
                counts["severe"] += 1
            elif level == "警告":
                counts["warning"] += 1
            elif level == "关注":
                counts["attention"] += 1
            else:
                counts["normal"] += 1

        health_summary = {
            "total": total_devices,
            **counts,
        }

        # --- Problem distribution ---
        cat_dist: dict[str, dict[str, int]] = {}
        area_dist: dict[str, dict[str, int]] = {}
        metric_dist: dict[str, dict[str, int]] = {}

        for dev in devices.values():
            score = LEVEL_SCORE.get(dev["diagnosis_level"], 0)
            if score <= 0 or not dev["online"]:
                continue
            level = dev["diagnosis_level"]
            level_key = {"关注": "attention", "警告": "warning", "严重": "severe"}.get(level)
            
            if level_key:
                cat = dev["category"]
                if cat not in cat_dist:
                    cat_dist[cat] = {"attention": 0, "warning": 0, "severe": 0}
                cat_dist[cat][level_key] += 1

                area = dev["area"]
                if area not in area_dist:
                    area_dist[area] = {"attention": 0, "warning": 0, "severe": 0}
                area_dist[area][level_key] += 1

            # Metric distribution uses individual metric levels
            for metric_label, metric_level in dev["triggered_metrics"].items():
                m_level_key = {"关注": "attention", "警告": "warning", "严重": "severe"}.get(metric_level)
                if m_level_key:
                    if metric_label not in metric_dist:
                        metric_dist[metric_label] = {"attention": 0, "warning": 0, "severe": 0}
                    metric_dist[metric_label][m_level_key] += 1

        def _sort_dist(dist: dict[str, dict[str, int]]) -> list[dict]:
            items = [{"name": name, **vals} for name, vals in dist.items()]
            items.sort(
                key=lambda x: (x["severe"], x["warning"], x["attention"]),
                reverse=True,
            )
            return items

        problem_distribution = {
            "byCategory": _sort_dist(cat_dist),
            "byArea": _sort_dist(area_dist),
            "byMetric": _sort_dist(metric_dist),
        }

        import json
        with open('/tmp/debug_dist.json', 'w') as f:
            json.dump(problem_distribution, f)

        # --- Fault device list ---
        now_dt = datetime.utcnow()
        fault_devices = []

        for dev in devices.values():
            score = LEVEL_SCORE.get(dev["diagnosis_level"], 0)
            if score <= 0 or not dev["online"]:
                continue

            # Duration: find earliest triggered time across this device's SNs
            earliest_trigger = None
            for sn in dev["sns"]:
                ft = first_triggered_map.get(sn)
                if ft and (earliest_trigger is None or ft < earliest_trigger):
                    earliest_trigger = ft

            duration_hours = None
            if earliest_trigger:
                delta = now_dt - earliest_trigger
                duration_hours = round(delta.total_seconds() / 3600, 1)

            # Trend: compare current level with previous cycle's level
            prev_max_score = -1
            for sn in dev["sns"]:
                prev_level = previous_level_map.get(sn, "未检测")
                ps = LEVEL_SCORE.get(prev_level, -1)
                if ps > prev_max_score:
                    prev_max_score = ps

            if prev_max_score < 0 or prev_max_score == score:
                trending = "stable"
            elif score > prev_max_score:
                trending = "worsening"
            else:
                trending = "improving"

            fault_devices.append({
                "deviceId": dev["device_id"],
                "deviceName": dev["device_name"],
                "deviceCode": dev["device_code"],
                "category": dev["category"],
                "area": dev["area"],
                "level": dev["diagnosis_level"],
                "levelScore": score,
                "metrics": sorted(dev["triggered_metrics"]),
                "durationHours": duration_hours,
                "trending": trending,
            })

        # Sort: worsening first, then by level desc, then by duration desc
        trend_order = {"worsening": 0, "stable": 1, "improving": 2}
        fault_devices.sort(
            key=lambda x: (
                trend_order.get(x["trending"], 1),
                -x["levelScore"],
                -(x["durationHours"] or 0),
            )
        )

        return {
            "healthSummary": health_summary,
            "problemDistribution": problem_distribution,
            "faultDevices": fault_devices,
        }
