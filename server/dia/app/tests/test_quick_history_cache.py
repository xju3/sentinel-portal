import json

from pub.services.quick_history_cache import (
    build_quick_diagnosis_snapshot,
    record_quick_diagnosis_snapshot,
)


class FakePipeline:
    def __init__(self, redis):
        self.redis = redis
        self.ops = []

    def lpush(self, key, value):
        self.ops.append(("lpush", key, value))
        return self

    def ltrim(self, key, start, end):
        self.ops.append(("ltrim", key, start, end))
        return self

    def set(self, key, value):
        self.ops.append(("set", key, value))
        return self

    def execute(self):
        for op in self.ops:
            if op[0] == "lpush":
                _, key, value = op
                self.redis.lists.setdefault(key, []).insert(0, value)
            elif op[0] == "ltrim":
                _, key, start, end = op
                self.redis.lists[key] = self.redis.lists.get(key, [])[start:end + 1]
            elif op[0] == "set":
                _, key, value = op
                self.redis.values[key] = value


class FakeRedis:
    def __init__(self):
        self.lists = {}
        self.values = {}

    def pipeline(self):
        return FakePipeline(self)


def _payload(task_id=""):
    return {
        "sn": "STL26SH0001",
        "ts_ms": 1780814415097,
        "temperature_c": 42.5,
        "requested_range_g": 2,
        "range_g": 2,
        "points": 4096,
        "fs_hz": 26667,
        "task_id": task_id,
        "sample_type": "normal",
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
                        "X": {"max_abs_g": 1.8, "clip_count": 0, "clip_ratio": 0},
                        "Y": {"max_abs_g": 0.2, "clip_count": 0, "clip_ratio": 0},
                        "Z": {"max_abs_g": 1.96, "clip_count": 1, "clip_ratio": 0.01},
                    },
                }
            ],
        },
        "axis_features": {
            "X": {"time": {"rms_vel_mm_s": 4.5}},
            "Y": {"time": {"rms_vel_mm_s": 2.1}},
            "Z": {"time": {"rms_vel_mm_s": 7.9}},
        },
    }


def test_build_quick_snapshot_extracts_fast_dispatch_fields():
    snapshot = build_quick_diagnosis_snapshot(
        report_id="r1",
        sn="STL26SH0001",
        payload=_payload(),
    )

    assert snapshot.temperature_c == 42.5
    assert snapshot.rms_vel_mm_s == {"X": 4.5, "Y": 2.1, "Z": 7.9}
    assert snapshot.quality["clipped"] is True
    assert snapshot.quality["near_clip"] is True
    assert snapshot.quality["clip_axes"] == ["Z"]
    assert not snapshot.is_task_report


def test_record_quick_snapshot_updates_last_regular_only_for_regular_reports(monkeypatch):
    fake_redis = FakeRedis()

    class FakeRedisManager:
        @staticmethod
        def get_client():
            return fake_redis

    monkeypatch.setattr("pub.services.quick_history_cache.redis_manager", FakeRedisManager)

    regular = record_quick_diagnosis_snapshot(
        report_id="r1",
        sn="STL26SH0001",
        payload=_payload(),
    )
    task = record_quick_diagnosis_snapshot(
        report_id="r2",
        sn="STL26SH0001",
        payload=_payload(task_id="task-1"),
    )

    assert regular is not None
    assert task is not None and task.is_task_report
    assert len(fake_redis.lists["dia:quick:history:STL26SH0001:recent"]) == 2

    last_regular = json.loads(fake_redis.values["dia:quick:last_regular:STL26SH0001"])
    assert last_regular["report_id"] == "r1"
    assert last_regular["task_id"] == ""
