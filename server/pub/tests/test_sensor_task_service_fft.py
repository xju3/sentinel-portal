from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from pub.services.sensor import sensor_task_service


class FakeExecuteResult:
    def __init__(self, scalar=None):
        self._scalar = scalar

    def scalar_one_or_none(self):
        return self._scalar


class FakeSession:
    def __init__(self, responses, *, get_map=None):
        self._responses = list(responses)
        self._get_map = dict(get_map or {})
        self.commit_calls = 0

    async def execute(self, _stmt):
        if not self._responses:
            raise AssertionError("Unexpected execute call")
        response = self._responses.pop(0)
        if callable(response):
            response = response(_stmt)
        return response

    async def get(self, model, key):
        return self._get_map.get((model, key))

    async def commit(self):
        self.commit_calls += 1

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_process_fft_metadata_background_rejects_non_99_action(monkeypatch):
    task_id = uuid4()
    task = SimpleNamespace(
        id=task_id,
        sn="SN-001",
        action=908,
    )
    session = FakeSession([FakeExecuteResult(task)])
    monkeypatch.setattr(sensor_task_service.db_manager, "SessionLocal", lambda: session)

    completed = await sensor_task_service.process_fft_metadata_background(task_id)

    assert completed is False
    assert session.commit_calls == 0


def test_fft_collection_spec_is_parameter_free_action_99():
    spec = sensor_task_service.build_fft_collection_spec()

    assert spec.action == 99
    assert spec.val == 0
    assert spec.kind == "fft_collection"
    assert "自动决定点数" in spec.description
    assert sensor_task_service.describe_collection_action(99, 0) == spec.description
    assert sensor_task_service.describe_collection_action(2086, 3) == (
        "系统任务：action=2086, val=3"
    )
