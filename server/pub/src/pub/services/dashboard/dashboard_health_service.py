"""
Dashboard Health Service - focused health overview for equipment managers.

Provides a single endpoint that returns three blocks of data:
1. Health summary (device counts by level)
2. Problem distribution (by category and area)
3. Fault device list (prioritized by severity, duration, and trend)
"""

import asyncio
import copy
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pub.manager.database import db_manager, redis_manager
from pub.models.device import DeviceCategory, DeviceInst, DeviceSpec, ProcessDevice, ProcessDeviceItem
from pub.models.diagnosis import Diagnosis, DiagnosisItem
from pub.models.customer import Area
from pub.models.sensor import CommunicationState, Sensor, SensorMonitoring
from pub.utils.redis_keys import (
    REDIS_KEY_DASHBOARD_HEALTH_DIRTY,
    REDIS_KEY_DASHBOARD_HEALTH_REFRESH_LOCK,
    REDIS_KEY_DASHBOARD_HEALTH_SNAPSHOT,
    REDIS_KEY_DIA_HEALTH_STATUS,
)

logger = logging.getLogger(__name__)

INT_TO_LEVEL = {
    0: "正常",
    1: "关注",
    2: "异常",
    3: "警告",
    4: "严重",
}

LEVEL_SCORE = {
    "未检测": -1,
    "正常": 0,
    "关注": 1,
    "异常": 2,
    "警告": 3,
    "严重": 4,
}

METRIC_LABELS = {
    0: "温度",
    1: "振动",
    2: "振动(Y轴)",
    3: "振动(Z轴)",
}

OFFLINE_AFTER_MS = 24 * 60 * 60 * 1000
HEALTH_SNAPSHOT_SOFT_TTL_SECONDS = 60
HEALTH_SNAPSHOT_HARD_TTL_SECONDS = 24 * 60 * 60
HEALTH_REFRESH_LOCK_SECONDS = 30
RELEASE_REFRESH_LOCK_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
end
return 0
"""


class DashboardHealthService:
    """Health-focused dashboard: summary → distribution → fault list."""

    @staticmethod
    def _get_redis_client():
        try:
            return redis_manager.get_client()
        except RuntimeError:
            return None

    @staticmethod
    def _snapshot_key(tenant_id: UUID) -> str:
        return REDIS_KEY_DASHBOARD_HEALTH_SNAPSHOT.format(tenant_id=tenant_id)

    @staticmethod
    def _refresh_lock_key(tenant_id: UUID) -> str:
        return REDIS_KEY_DASHBOARD_HEALTH_REFRESH_LOCK.format(tenant_id=tenant_id)

    @staticmethod
    def _decorate_snapshot(
        data: dict,
        generated_at_ms: int,
        *,
        stale: bool,
        source: str,
    ) -> dict:
        result = copy.deepcopy(data)
        result["snapshot"] = {
            "generatedAt": datetime.fromtimestamp(
                generated_at_ms / 1000, tz=timezone.utc
            ).isoformat(),
            "stale": stale,
            "refreshing": False,
            "source": source,
        }
        return result

    @staticmethod
    async def _get_cached_snapshot(tenant_id: UUID) -> dict | None:
        client = DashboardHealthService._get_redis_client()
        if not client:
            return None
        try:
            raw_snapshot, dirty_at = await asyncio.gather(
                asyncio.to_thread(client.get, DashboardHealthService._snapshot_key(tenant_id)),
                asyncio.to_thread(
                    client.hget,
                    REDIS_KEY_DASHBOARD_HEALTH_DIRTY,
                    str(tenant_id),
                ),
            )
            if not raw_snapshot:
                return None
            cached = json.loads(raw_snapshot)
            generated_at_ms = int(cached["generatedAtMs"])
            observed_at_ms = int(cached.get("observedAtMs", generated_at_ms))
            age_seconds = max(0, (int(time.time() * 1000) - generated_at_ms) / 1000)
            stale = age_seconds >= HEALTH_SNAPSHOT_SOFT_TTL_SECONDS
            if dirty_at is not None and int(dirty_at) > observed_at_ms:
                stale = True
            return DashboardHealthService._decorate_snapshot(
                cached["data"],
                generated_at_ms,
                stale=stale,
                source="redis",
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("Invalid dashboard snapshot for tenant %s: %s", tenant_id, exc)
        except Exception as exc:
            logger.warning("Failed to read dashboard snapshot for tenant %s: %s", tenant_id, exc)
        return None

    @staticmethod
    async def _set_cached_snapshot(
        tenant_id: UUID,
        data: dict,
        observed_at_ms: int,
    ) -> dict:
        generated_at_ms = int(time.time() * 1000)
        client = DashboardHealthService._get_redis_client()
        if client:
            payload = json.dumps(
                {
                    "generatedAtMs": generated_at_ms,
                    "observedAtMs": observed_at_ms,
                    "data": data,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
            try:
                await asyncio.to_thread(
                    client.setex,
                    DashboardHealthService._snapshot_key(tenant_id),
                    HEALTH_SNAPSHOT_HARD_TTL_SECONDS,
                    payload,
                )
            except Exception as exc:
                logger.warning("Failed to cache dashboard snapshot for tenant %s: %s", tenant_id, exc)
        return DashboardHealthService._decorate_snapshot(
            data,
            generated_at_ms,
            stale=False,
            source="database",
        )

    @staticmethod
    async def get_health_dashboard(
        session: AsyncSession,
        tenant_id: UUID,
    ) -> dict:
        cached = await DashboardHealthService._get_cached_snapshot(tenant_id)
        if cached is not None:
            return cached

        observed_at_ms = int(time.time() * 1000)
        data = await DashboardHealthService._build_health_dashboard(session, tenant_id)
        return await DashboardHealthService._set_cached_snapshot(
            tenant_id,
            data,
            observed_at_ms,
        )

    @staticmethod
    async def refresh_health_dashboard(tenant_id: UUID) -> None:
        """Refresh one tenant snapshot without delaying the dashboard response."""
        client = DashboardHealthService._get_redis_client()
        if not client or db_manager.SessionLocal is None:
            return

        lock_key = DashboardHealthService._refresh_lock_key(tenant_id)
        lock_token = uuid4().hex
        acquired = False
        try:
            acquired = await asyncio.to_thread(
                client.set,
                lock_key,
                lock_token,
                nx=True,
                ex=HEALTH_REFRESH_LOCK_SECONDS,
            )
            if not acquired:
                return
            observed_at_ms = int(time.time() * 1000)
            async with db_manager.SessionLocal() as session:
                data = await DashboardHealthService._build_health_dashboard(
                    session, tenant_id
                )
                await DashboardHealthService._set_cached_snapshot(
                    tenant_id,
                    data,
                    observed_at_ms,
                )
        except Exception:
            logger.exception("Failed to refresh dashboard snapshot for tenant %s", tenant_id)
        finally:
            if acquired:
                try:
                    await asyncio.to_thread(
                        client.eval,
                        RELEASE_REFRESH_LOCK_SCRIPT,
                        1,
                        lock_key,
                        lock_token,
                    )
                except Exception:
                    logger.debug("Failed to release dashboard refresh lock %s", lock_key)

    @staticmethod
    async def warm_health_dashboard(tenant_id: UUID) -> None:
        """Build a startup snapshot only when Redis has no fresh copy."""
        cached = await DashboardHealthService._get_cached_snapshot(tenant_id)
        if cached is None or cached["snapshot"]["stale"]:
            await DashboardHealthService.refresh_health_dashboard(tenant_id)

    @staticmethod
    async def _build_health_dashboard(session: AsyncSession, tenant_id: UUID) -> dict:
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

        # 3. Query communication states for online/offline
        comm_states = await DashboardHealthService._query_comm_states(
            session, monitored_sns
        )

        # 4. Determine online status per device
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

        # 5. Fetch overall level from Redis cache for all monitored devices.
        # 正常结果只存在于这个 Hash；Redis miss 必须保留为“未检测”，不能猜成正常。
        redis_client = DashboardHealthService._get_redis_client()
        fault_device_ids = set()
        
        if redis_client and devices:
            device_ids_list = list(devices.keys())
            try:
                redis_query_keys = [str(UUID(d)) for d in device_ids_list]
                
                cached_levels = await asyncio.to_thread(redis_client.hmget, REDIS_KEY_DIA_HEALTH_STATUS, *redis_query_keys)
                
                for dev_id, level_str in zip(device_ids_list, cached_levels):
                    if level_str is not None:
                        dev = devices[dev_id]
                        overall_score = int(level_str)
                        overall_level_str = INT_TO_LEVEL.get(overall_score, "正常")
                        dev["has_diagnosis"] = True
                        dev["diagnosis_score"] = overall_score
                        dev["diagnosis_level"] = overall_level_str
                        
                        if overall_score > 0:
                            fault_device_ids.add(dev_id)
                    # Cache miss: 设备尚未被诊断，或 Redis 重启后尚未恢复
                    # 保持默认值 diagnosis_level="未检测"，不回源数据库
                    # 理由：数据库只存异常记录，回源必然误判为异常
            except Exception as e:
                logger.error("Failed to fetch health status from Redis: %s", e)

        # 6. For fault devices, query detailed metrics, duration, and trend
        latest_results = {}
        first_triggered_map = {}
        previous_level_map = {}
        issue_occurrences = {}
        device_occurrences = {}
        
        if fault_device_ids:
            fault_uuids = {UUID(d) for d in fault_device_ids}
            latest_results = await DashboardHealthService._query_latest_diagnosis(
                session, fault_uuids
            )
            first_triggered_map = await DashboardHealthService._query_first_triggered(
                session, fault_device_ids
            )
            previous_level_map = await DashboardHealthService._query_previous_levels(
                session, fault_device_ids
            )
            issue_occurrences = await DashboardHealthService._query_issue_occurrences(
                session, fault_uuids
            )
            device_occurrences = await DashboardHealthService._query_device_occurrences(
                session, fault_uuids
            )
            
            # Apply triggered metrics for fault devices
            for dev_id, metric_results in latest_results.items():
                if dev_id not in devices:
                    continue
                dev = devices[dev_id]
                for metric_id, (diag, item) in metric_results.items():
                    level_str = INT_TO_LEVEL.get(item.level, "正常")
                    score = LEVEL_SCORE.get(level_str, 0)
                    if score > 0:
                        label = METRIC_LABELS.get(metric_id, str(metric_id))
                        current_metric_level = dev["triggered_metrics"].get(label)
                        if not current_metric_level or score > LEVEL_SCORE.get(current_metric_level, 0):
                            dev["triggered_metrics"][label] = level_str

        # 8. Assemble response
        return DashboardHealthService._assemble_response(
            devices=devices,
            total_devices=total_devices,
            sn_to_devices=sn_to_devices,
            first_triggered_map=first_triggered_map,
            previous_level_map=previous_level_map,
            latest_results=latest_results,
            issue_occurrences=issue_occurrences,
            device_occurrences=device_occurrences,
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
        session: AsyncSession, device_ids: set[UUID]
    ) -> dict[str, dict[int, tuple[Diagnosis, DiagnosisItem]]]:
        """Get latest DiagnosisItem per (device_id, metric_id)."""
        if not device_ids:
            return {}
        ranked = (
            select(
                DiagnosisItem.id.label("id"),
                func.row_number()
                .over(
                    partition_by=(Diagnosis.device_id, DiagnosisItem.metric_id),
                    order_by=(
                        desc(Diagnosis.diagnosed_at),
                    ),
                )
                .label("row_num"),
            )
            .join(Diagnosis, DiagnosisItem.diagnosis_id == Diagnosis.id)
            .where(Diagnosis.device_id.in_(list(device_ids)))
            .subquery()
        )
        stmt = (
            select(Diagnosis, DiagnosisItem)
            .join(DiagnosisItem, DiagnosisItem.diagnosis_id == Diagnosis.id)
            .join(ranked, DiagnosisItem.id == ranked.c.id)
            .where(ranked.c.row_num == 1)
        )
        rows = (await session.execute(stmt)).all()
        latest = {}
        for diag, item in rows:
            dev_id_str = str(diag.device_id)
            latest.setdefault(dev_id_str, {})[item.metric_id] = (diag, item)
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
        session: AsyncSession, device_ids: set[str]
    ) -> dict[str, datetime]:
        """Get earliest triggered diagnosis time per device (for duration calculation)."""
        if not device_ids:
            return {}
        uuid_ids = [UUID(d) for d in device_ids]
        stmt = (
            select(
                Diagnosis.device_id,
                func.min(Diagnosis.diagnosed_at).label("first_at"),
            )
            .where(
                Diagnosis.device_id.in_(uuid_ids),
                Diagnosis.overall_level > 0,
                Diagnosis.resampling == 0,
            )
            .group_by(Diagnosis.device_id)
        )
        rows = await session.execute(stmt)
        return {str(row.device_id): row.first_at for row in rows if row.first_at}

    @staticmethod
    async def _query_previous_levels(
        session: AsyncSession, device_ids: set[str]
    ) -> dict[str, str]:
        """Get the second-latest diagnosis level per device to determine trend."""
        if not device_ids:
            return {}
        uuid_ids = [UUID(d) for d in device_ids]
        
        ranked = (
            select(
                Diagnosis.device_id,
                Diagnosis.overall_level,
                func.row_number()
                .over(
                    partition_by=Diagnosis.device_id,
                    order_by=(desc(Diagnosis.diagnosed_at)),
                )
                .label("row_num"),
            )
            .where(
                Diagnosis.device_id.in_(uuid_ids),
                Diagnosis.resampling == 0,
            )
            .subquery()
        )
        
        stmt = (
            select(
                ranked.c.device_id,
                ranked.c.overall_level,
            )
            .where(ranked.c.row_num == 2)
        )
        rows = await session.execute(stmt)
        
        prev: dict[str, int] = {}
        for row in rows:
            dev_str = str(row.device_id)
            score = row.overall_level
            if dev_str not in prev or score > prev[dev_str]:
                prev[dev_str] = score
                
        return {d: INT_TO_LEVEL.get(s, "未检测") for d, s in prev.items()}

    @staticmethod
    async def _query_issue_occurrences(
        session: AsyncSession,
        device_ids: set[UUID],
    ) -> dict[str, dict[int, dict[str, Any]]]:
        """Summarize confirmed anomaly detections without claiming continuity."""
        if not device_ids:
            return {}
        stmt = (
            select(
                Diagnosis.device_id,
                DiagnosisItem.metric_id,
                func.count(DiagnosisItem.id).label("occurrence_count"),
                func.min(Diagnosis.diagnosed_at).label("first_detected_at"),
                func.max(Diagnosis.diagnosed_at).label("last_detected_at"),
            )
            .join(DiagnosisItem, DiagnosisItem.diagnosis_id == Diagnosis.id)
            .where(
                Diagnosis.device_id.in_(list(device_ids)),
                Diagnosis.overall_level > 0,
                Diagnosis.resampling == 0,
                DiagnosisItem.level > 0,
                DiagnosisItem.resampling == 0,
            )
            .group_by(Diagnosis.device_id, DiagnosisItem.metric_id)
        )
        rows = (await session.execute(stmt)).all()
        result: dict[str, dict[int, dict[str, Any]]] = {}
        for row in rows:
            result.setdefault(str(row.device_id), {})[row.metric_id] = {
                "occurrenceCount": int(row.occurrence_count or 0),
                "firstDetectedAt": (
                    row.first_detected_at.isoformat()
                    if row.first_detected_at
                    else None
                ),
                "lastDetectedAt": (
                    row.last_detected_at.isoformat()
                    if row.last_detected_at
                    else None
                ),
            }
        return result

    @staticmethod
    async def _query_device_occurrences(
        session: AsyncSession,
        device_ids: set[UUID],
    ) -> dict[str, dict[str, Any]]:
        """Count confirmed anomaly diagnosis events at device level."""
        if not device_ids:
            return {}
        stmt = (
            select(
                Diagnosis.device_id,
                func.count(func.distinct(Diagnosis.id)).label("occurrence_count"),
                func.min(Diagnosis.diagnosed_at).label("first_detected_at"),
                func.max(Diagnosis.diagnosed_at).label("last_detected_at"),
            )
            .where(
                Diagnosis.device_id.in_(list(device_ids)),
                Diagnosis.overall_level > 0,
                Diagnosis.resampling == 0,
            )
            .group_by(Diagnosis.device_id)
        )
        rows = (await session.execute(stmt)).all()
        return {
            str(row.device_id): {
                "occurrenceCount": int(row.occurrence_count or 0),
                "firstDetectedAt": (
                    row.first_detected_at.isoformat()
                    if row.first_detected_at
                    else None
                ),
                "lastDetectedAt": (
                    row.last_detected_at.isoformat()
                    if row.last_detected_at
                    else None
                ),
            }
            for row in rows
        }

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
        latest_results: dict,
        issue_occurrences: dict[str, dict[int, dict[str, Any]]],
        device_occurrences: dict[str, dict[str, Any]],
        now_ms: int,
    ) -> dict[str, Any]:
        # --- Health summary ---
        counts = {
            "normal": 0,
            "attention": 0,
            "abnormal": 0,
            "warning": 0,
            "severe": 0,
            "uninspected": 0,
            "offline": 0,
            "unconfigured": 0,
        }
        monitored_count = 0

        for dev in devices.values():
            if not dev["sns"]:
                counts["unconfigured"] += 1
                continue
            monitored_count += 1
            if not dev["online"]:
                counts["offline"] += 1
            
            level = dev["diagnosis_level"]
            if level == "严重":
                counts["severe"] += 1
            elif level == "警告":
                counts["warning"] += 1
            elif level == "异常":
                counts["abnormal"] += 1
            elif level == "关注":
                counts["attention"] += 1
            elif level == "正常":
                counts["normal"] += 1
            else:
                counts["uninspected"] += 1

        health_summary = {
            "total": total_devices,
            "monitored": monitored_count,
            "online": monitored_count - counts["offline"],
            "diagnosed": monitored_count - counts["uninspected"],
            **counts,
        }

        # --- Problem distribution ---
        cat_dist: dict[str, dict[str, int]] = {}
        area_dist: dict[str, dict[str, int]] = {}
        metric_dist: dict[str, dict[str, int]] = {}

        for dev in devices.values():
            score = LEVEL_SCORE.get(dev["diagnosis_level"], 0)
            if score <= 0:
                continue
            level = dev["diagnosis_level"]
            level_key = {"关注": "attention", "异常": "abnormal", "警告": "warning", "严重": "severe"}.get(level)
            
            if level_key:
                cat = dev["category"]
                if cat not in cat_dist:
                    cat_dist[cat] = {"attention": 0, "abnormal": 0, "warning": 0, "severe": 0}
                cat_dist[cat][level_key] += 1

                area = dev["area"]
                if area not in area_dist:
                    area_dist[area] = {"attention": 0, "abnormal": 0, "warning": 0, "severe": 0}
                area_dist[area][level_key] += 1

            # Metric distribution uses individual metric levels
            for metric_label, metric_level in dev["triggered_metrics"].items():
                m_level_key = {"关注": "attention", "异常": "abnormal", "警告": "warning", "严重": "severe"}.get(metric_level)
                if m_level_key:
                    if metric_label not in metric_dist:
                        metric_dist[metric_label] = {"attention": 0, "abnormal": 0, "warning": 0, "severe": 0}
                    metric_dist[metric_label][m_level_key] += 1

        def _sort_dist(dist: dict[str, dict[str, int]]) -> list[dict]:
            items = [{"name": name, **vals} for name, vals in dist.items()]
            items.sort(
                key=lambda x: (x["severe"], x["warning"], x.get("abnormal", 0), x["attention"]),
                reverse=True,
            )
            return items

        problem_distribution = {
            "byCategory": _sort_dist(cat_dist),
            "byArea": _sort_dist(area_dist),
            "byMetric": _sort_dist(metric_dist),
        }



        # --- Fault device list ---
        now_dt = datetime.utcnow()
        fault_devices = []

        for dev in devices.values():
            score = LEVEL_SCORE.get(dev["diagnosis_level"], 0)
            if score <= 0:
                continue

            # Duration: find earliest triggered time across this device
            earliest_trigger = first_triggered_map.get(dev["device_id"])

            duration_hours = None
            if earliest_trigger:
                delta = now_dt - earliest_trigger
                duration_hours = round(delta.total_seconds() / 3600, 1)

            # Trend: compare current level with previous cycle's level
            prev_level = previous_level_map.get(dev["device_id"], "未检测")
            prev_max_score = LEVEL_SCORE.get(prev_level, -1)

            if prev_max_score < 0 or prev_max_score == score:
                trending = "stable"
            elif score > prev_max_score:
                trending = "worsening"
            else:
                trending = "improving"

            # Build per-metric diagnosis detail
            diagnosis_details = []
            metric_results = latest_results.get(dev["device_id"], {})
            metric_occurrences = issue_occurrences.get(dev["device_id"], {})
            for metric_id, (diag, item) in metric_results.items():
                item_level_str = INT_TO_LEVEL.get(item.level, "正常")
                item_score = LEVEL_SCORE.get(item_level_str, 0)
                if item_score <= 0:
                    continue
                evidence = item.evidence or {}
                occurrence = metric_occurrences.get(metric_id, {})
                ratio = evidence.get("vibration_budget_ratio")
                if ratio is None:
                    ratio = evidence.get("thermal_budget_ratio")
                diagnosis_details.append({
                    "metricId": metric_id,
                    "metricLabel": METRIC_LABELS.get(metric_id, str(metric_id)),
                    "level": item_level_str,
                    "levelScore": item_score,
                    "description": item.description,
                    "diagnosedAt": diag.diagnosed_at.isoformat() if diag.diagnosed_at else None,
                    "occurrenceCount": occurrence.get("occurrenceCount", 0),
                    "firstDetectedAt": occurrence.get("firstDetectedAt"),
                    "lastDetectedAt": occurrence.get("lastDetectedAt"),
                    "evidence": {
                        "ratio": ratio,
                        "current": evidence.get("current"),
                        "healthyMedian": evidence.get("healthy_median"),
                        "peerMedian": evidence.get("peer_median"),
                        "stSlope": evidence.get("st_slope"),
                        "mtSlope": evidence.get("mt_slope"),
                        "mutation": evidence.get("mutation"),
                        "confirmationStatus": evidence.get("confirmation_status"),
                    },
                })
            # Sort by severity desc
            diagnosis_details.sort(key=lambda x: -x["levelScore"])
            device_occurrence = device_occurrences.get(dev["device_id"], {})
            occurrence_count = device_occurrence.get("occurrenceCount", 0)
            first_detected_at = device_occurrence.get("firstDetectedAt")
            last_detected_at = device_occurrence.get("lastDetectedAt")
            if trending == "worsening":
                issue_state = "worsening"
            elif trending == "improving":
                issue_state = "improving"
            elif occurrence_count > 1:
                issue_state = "repeated"
            else:
                issue_state = "new"

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
                "issueState": issue_state,
                "occurrenceCount": occurrence_count,
                "firstDetectedAt": first_detected_at,
                "lastDetectedAt": last_detected_at,
                "diagnosisDetails": diagnosis_details,
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
        issue_summary = {
            "new": 0,
            "repeated": 0,
            "worsening": 0,
            "improving": 0,
            "pendingConfirmation": 0,
        }
        for device in fault_devices:
            issue_state = device["issueState"]
            if issue_state in issue_summary:
                issue_summary[issue_state] += 1
            if any(
                detail["evidence"].get("confirmationStatus")
                not in (None, "confirmed")
                for detail in device["diagnosisDetails"]
            ):
                issue_summary["pendingConfirmation"] += 1

        return {
            "healthSummary": health_summary,
            "issueSummary": issue_summary,
            "problemDistribution": problem_distribution,
            "faultDevices": fault_devices,
        }
