import pytest

from app.handler.temperature import TemperatureDiagnosis
from app.handler.vibration import VibrationDiagnosis


@pytest.mark.asyncio
async def test_temperature_mutation_compares_with_previous_report(monkeypatch):
    async def get_recent_trend(_location_id, _metric):
        return [
            {"ts_ms": 1_000, "value": 10.0},
            {"ts_ms": 2_000, "value": 30.0},
        ]

    monkeypatch.setattr(
        "app.handler.temperature.TrendCacheService.get_recent_trend",
        get_recent_trend,
    )

    result = await TemperatureDiagnosis.analyze(
        "device-1",
        "location-1",
        30.0,
        {
            "thresholds": {"temperature": {"baseline": 85, "rt_max_delta": 15}},
            "ambient_temperature": None,
            "peer_group": {"enabled": False},
        },
        current_ts_ms=2_000,
    )

    assert result["severity"] == "warning"
    assert result["evidence"]["last_temp"] == 10.0
    assert result["evidence"]["mutation"] == 20.0
    assert result["evidence"]["schema_version"] == 2
    assert result["evidence"]["fault_type"] == "temperature"
    assert result["evidence"]["result"]["primary_rule"] == (
        "temperature.realtime_mutation"
    )
    mutation_check = next(
        check
        for check in result["evidence"]["checks"]
        if check["code"] == "temperature.realtime_mutation"
    )
    assert mutation_check["threshold"] == 15.0
    assert mutation_check["triggered"] is True


@pytest.mark.asyncio
async def test_vibration_mutation_compares_with_previous_report(monkeypatch):
    async def get_active_baseline(_device_id, _metric):
        return 0.0

    async def get_recent_trend(_location_id, _metric):
        return [
            {"ts_ms": 1_000, "value": 1.0},
            {"ts_ms": 2_000, "value": 7.0},
        ]

    monkeypatch.setattr(
        "app.handler.vibration.BaselineService.get_active_baseline",
        get_active_baseline,
    )
    monkeypatch.setattr(
        "app.handler.vibration.TrendCacheService.get_recent_trend",
        get_recent_trend,
    )

    result = await VibrationDiagnosis.analyze(
        "device-1",
        "location-1",
        7.0,
        {
            "thresholds": {
                "vibration": {
                    "baseline": 11,
                    "rt_max_delta": 5,
                }
            },
            "peer_group": {"enabled": False},
        },
        current_ts_ms=2_000,
    )

    assert result["severity"] == "warning"
    assert result["evidence"]["last_val"] == 1.0
    assert result["evidence"]["mutation"] == 6.0
    assert result["evidence"]["schema_version"] == 2
    assert result["evidence"]["fault_type"] == "vibration"
    assert result["evidence"]["result"]["primary_rule"] == (
        "vibration.realtime_mutation"
    )


@pytest.mark.asyncio
async def test_vibration_budget_ratio_alone_does_not_create_fault(monkeypatch):
    async def get_active_baseline(_device_id, _metric):
        return 0.0

    async def get_recent_trend(_location_id, _metric):
        return []

    monkeypatch.setattr(
        "app.handler.vibration.BaselineService.get_active_baseline",
        get_active_baseline,
    )
    monkeypatch.setattr(
        "app.handler.vibration.TrendCacheService.get_recent_trend",
        get_recent_trend,
    )

    result = await VibrationDiagnosis.analyze(
        "device-1",
        "location-1",
        3.0,
        {
            "thresholds": {"vibration": {"baseline": 11}},
            "peer_group": {"enabled": False},
        },
        current_ts_ms=2_000,
    )

    assert result["status"] == "ok"
    assert result["severity"] == "info"
    assert result["evidence"]["context"]["budget_ratio"] > 0.20
    assert result["evidence"]["result"]["triggered_rules"] == []
