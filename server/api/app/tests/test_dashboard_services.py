import json
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest

from pub.services.dashboard.dashboard_health_service import DashboardHealthService
from pub.services.dashboard.dashboard_service import DashboardService
from pub.utils.redis_keys import REDIS_KEY_DASHBOARD_HEALTH_DIRTY


class FakeRedis:
    def __init__(self):
        self.values: dict[str, str] = {}
        self.hashes: dict[str, dict[str, str]] = {}

    def get(self, key: str):
        return self.values.get(key)

    def hget(self, key: str, field: str):
        return self.hashes.get(key, {}).get(field)

    def hdel(self, key: str, field: str):
        return self.hashes.get(key, {}).pop(field, None)

    def setex(self, key: str, _ttl: int, value: str):
        self.values[key] = value


def test_health_summary_keeps_uninspected_out_of_normal():
    devices = {
        "normal": {
            "device_id": "normal",
            "device_name": "Normal",
            "device_code": "N",
            "category": "Pump",
            "area": "A",
            "sns": {"SN-1"},
            "online": True,
            "diagnosis_level": "正常",
            "triggered_metrics": {},
        },
        "uninspected": {
            "device_id": "uninspected",
            "device_name": "Unknown",
            "device_code": "U",
            "category": "Pump",
            "area": "A",
            "sns": {"SN-2"},
            "online": False,
            "diagnosis_level": "未检测",
            "triggered_metrics": {},
        },
        "unconfigured": {
            "device_id": "unconfigured",
            "device_name": "No sensor",
            "device_code": "X",
            "category": "Pump",
            "area": "A",
            "sns": set(),
            "online": False,
            "diagnosis_level": "未检测",
            "triggered_metrics": {},
        },
    }

    result = DashboardHealthService._assemble_response(
        devices=devices,
        total_devices=3,
        sn_to_devices={},
        first_triggered_map={},
        previous_level_map={},
        latest_results={},
        issue_occurrences={},
        device_occurrences={},
        now_ms=0,
    )

    assert result["healthSummary"]["normal"] == 1
    assert result["healthSummary"]["uninspected"] == 1
    assert result["healthSummary"]["unconfigured"] == 1
    assert result["healthSummary"]["monitored"] == 2
    assert result["healthSummary"]["online"] == 1


def test_device_repetition_counts_diagnosis_events_across_metrics():
    device_id = str(uuid4())
    devices = {
        device_id: {
            "device_id": device_id,
            "device_name": "Repeated",
            "device_code": "R",
            "category": "Pump",
            "area": "A",
            "sns": {"SN-1"},
            "online": True,
            "diagnosis_level": "关注",
            "triggered_metrics": {"温度": "关注"},
        }
    }
    diagnosis = SimpleNamespace(diagnosed_at=None)
    item = SimpleNamespace(
        level=1,
        description="temperature rise",
        evidence={},
    )

    result = DashboardHealthService._assemble_response(
        devices=devices,
        total_devices=1,
        sn_to_devices={},
        first_triggered_map={},
        previous_level_map={},
        latest_results={device_id: {0: (diagnosis, item)}},
        issue_occurrences={
            device_id: {
                0: {
                    "occurrenceCount": 1,
                    "firstDetectedAt": "2026-07-27T08:00:00",
                    "lastDetectedAt": "2026-07-27T08:00:00",
                }
            }
        },
        device_occurrences={
            device_id: {
                "occurrenceCount": 2,
                "firstDetectedAt": "2026-07-26T08:00:00",
                "lastDetectedAt": "2026-07-27T08:00:00",
            }
        },
        now_ms=0,
    )

    assert result["faultDevices"][0]["occurrenceCount"] == 2
    assert result["faultDevices"][0]["issueState"] == "repeated"


@pytest.mark.asyncio
async def test_health_snapshot_marks_dirty_tenant_as_stale(monkeypatch):
    tenant_id = uuid4()
    redis = FakeRedis()
    snapshot_key = DashboardHealthService._snapshot_key(tenant_id)
    redis.values[snapshot_key] = json.dumps(
        {
            "generatedAtMs": 1_000,
            "data": {
                "healthSummary": {},
                "issueSummary": {},
                "problemDistribution": {},
                "faultDevices": [],
            },
        }
    )
    redis.hashes[REDIS_KEY_DASHBOARD_HEALTH_DIRTY] = {str(tenant_id): "1001"}
    monkeypatch.setattr(
        DashboardHealthService,
        "_get_redis_client",
        staticmethod(lambda: redis),
    )

    result = await DashboardHealthService._get_cached_snapshot(tenant_id)

    assert result is not None
    assert result["snapshot"]["stale"] is True
    assert result["snapshot"]["source"] == "redis"


@pytest.mark.asyncio
async def test_calendar_cache_is_tenant_scoped_and_does_not_mutate_response(monkeypatch):
    tenant_id = uuid4()
    redis = FakeRedis()
    monkeypatch.setattr(
        DashboardService,
        "_get_redis_client",
        staticmethod(lambda: redis),
    )
    today = date(2026, 7, 28)
    data = {
        "year": 2026,
        "months": [
            {
                "month": 7,
                "days": [{"date": today.isoformat(), "count": 4, "level": 2}],
            }
        ],
        "start_at": "2026-01-01",
    }

    await DashboardService._set_cached_full_calendar(tenant_id, data, today)

    assert data["months"][0]["days"][0]["count"] == 4
    assert len(redis.values) == 1
    key, raw = next(iter(redis.values.items()))
    assert str(tenant_id) in key
    assert json.loads(raw)["months"][0]["days"][0]["count"] == 0
