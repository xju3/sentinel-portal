from copy import deepcopy

from app.handler.quality import diagnose_quality
from pub.services.diagnosis_service import DiagnosisResultService


def _payload() -> dict:
    return {
        "report_id": "r1",
        "sn": "STL26SH0001",
        "requested_range_g": 2,
        "range_g": 2,
        "quality": {
            "status": "ok",
            "auto_range": False,
            "attempts": [
                {
                    "range_g": 2,
                    "accepted": True,
                    "reason": "ok",
                    "clip_threshold_g": 1.96,
                    "axes": {
                        "X": {"max_abs_g": 0.176, "clip_count": 0, "clip_ratio": 0},
                        "Y": {"max_abs_g": 0.047, "clip_count": 0, "clip_ratio": 0},
                        "Z": {"max_abs_g": 0.969, "clip_count": 0, "clip_ratio": 0},
                    },
                }
            ],
        },
    }


def test_quality_accepts_ok_payload():
    result = diagnose_quality("r1", "STL26SH0001", _payload())

    assert result.metric == "quality"
    assert result.usable
    assert result.conclusion.level == "正常"
    assert [item.name for item in result.conclusion.items] == [
        "质量状态",
        "有效采样",
        "轴质量",
        "量程一致性",
    ]

    data, items = DiagnosisResultService.metric_result_to_record_data(result, report_ts=123)
    assert data["metric"] == "quality"
    assert data["level"] == "正常"
    assert data["report_ts"] == 123
    assert [item["name"] for item in items] == ["质量状态", "有效采样", "轴质量", "量程一致性"]


def test_quality_rejects_non_ok_status():
    payload = _payload()
    payload["quality"]["status"] = "bad"

    result = diagnose_quality("r1", "STL26SH0001", payload)

    assert not result.usable
    assert result.conclusion.level == "严重"
    assert result.conclusion.items[0].name == "质量状态"
    assert result.conclusion.items[0].triggered


def test_quality_rejects_without_accepted_attempt():
    payload = _payload()
    payload["quality"]["attempts"][0]["accepted"] = False

    result = diagnose_quality("r1", "STL26SH0001", payload)

    assert not result.usable
    assert result.conclusion.level == "严重"
    assert result.conclusion.items[1].name == "有效采样"
    assert result.conclusion.items[1].triggered


def test_quality_rejects_heavy_clipping():
    payload = deepcopy(_payload())
    payload["quality"]["attempts"][0]["axes"]["X"]["clip_count"] = 50
    payload["quality"]["attempts"][0]["axes"]["X"]["clip_ratio"] = 0.02

    result = diagnose_quality("r1", "STL26SH0001", payload)

    assert not result.usable
    assert result.conclusion.level == "严重"
    assert result.conclusion.items[2].name == "轴质量"
    assert result.conclusion.items[2].triggered


def test_quality_warns_but_allows_minor_clipping():
    payload = deepcopy(_payload())
    payload["quality"]["attempts"][0]["axes"]["X"]["clip_count"] = 1
    payload["quality"]["attempts"][0]["axes"]["X"]["clip_ratio"] = 0.0001

    result = diagnose_quality("r1", "STL26SH0001", payload)

    assert result.usable
    assert result.conclusion.level == "警告"
    assert result.conclusion.items[2].name == "轴质量"
    assert result.conclusion.items[2].triggered
