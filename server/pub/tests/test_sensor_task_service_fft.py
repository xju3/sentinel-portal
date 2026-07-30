from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
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


def test_resampling_spec_is_fixed_action_53_three_passes():
    spec = sensor_task_service.build_resampling_spec()

    assert spec.action == 53
    assert spec.val == 3
    assert spec.kind == "resampling"
    assert sensor_task_service.describe_collection_action(53, 3) == spec.description


@pytest.mark.asyncio
async def test_daily_fft_is_created_when_no_recent_or_open_work(monkeypatch):
    session = FakeSession(
        [
            FakeExecuteResult(None),
            FakeExecuteResult(None),
        ]
    )
    expected = SimpleNamespace(id=uuid4(), action=99, task_purpose="FFT_DAILY")
    create_fft = AsyncMock(return_value=expected)
    monkeypatch.setattr(
        sensor_task_service,
        "create_fft_collection_task",
        create_fft,
    )

    task = await sensor_task_service.ensure_daily_fft_task(
        session=session,
        sn="SN-001",
        now=datetime(2026, 7, 30, 12, 0, 0),
    )

    assert task is expected
    create_fft.assert_awaited_once()
    assert create_fft.await_args.kwargs["task_purpose"] == "FFT_DAILY"


@pytest.mark.asyncio
async def test_daily_fft_is_not_created_during_open_resampling(monkeypatch):
    session = FakeSession(
        [
            FakeExecuteResult(
                SimpleNamespace(id=uuid4(), action=53, status=2)
            ),
        ]
    )
    create_fft = AsyncMock()
    monkeypatch.setattr(
        sensor_task_service,
        "create_fft_collection_task",
        create_fft,
    )

    task = await sensor_task_service.ensure_daily_fft_task(
        session=session,
        sn="SN-001",
    )

    assert task is None
    create_fft.assert_not_awaited()


@pytest.mark.asyncio
async def test_daily_fft_is_not_created_with_recent_success(monkeypatch):
    now = datetime(2026, 7, 30, 12, 0, 0)
    session = FakeSession(
        [
            FakeExecuteResult(None),
            FakeExecuteResult(
                SimpleNamespace(
                    action=99,
                    status=1,
                    complete_time=now - timedelta(hours=23),
                )
            ),
        ]
    )
    create_fft = AsyncMock()
    monkeypatch.setattr(
        sensor_task_service,
        "create_fft_collection_task",
        create_fft,
    )

    task = await sensor_task_service.ensure_daily_fft_task(
        session=session,
        sn="SN-001",
        now=now,
    )

    assert task is None
    create_fft.assert_not_awaited()


@pytest.mark.asyncio
async def test_resampling_followup_reuses_durable_link_after_fft_completion():
    resampling_id = uuid4()
    fft_id = uuid4()
    resampling = SimpleNamespace(
        id=resampling_id,
        sn="SN-001",
        action=53,
        val=3,
        followup_fft_task_id=fft_id,
    )
    completed_fft = SimpleNamespace(
        id=fft_id,
        sn="SN-001",
        action=99,
        status=1,
    )
    session = FakeSession(
        [
            FakeExecuteResult(resampling),
            FakeExecuteResult(completed_fft),
        ]
    )

    task = await sensor_task_service.ensure_resampling_followup_fft_task(
        session=session,
        resampling_task_id=resampling_id,
        reason="duplicate final upload",
    )

    assert task is completed_fft
    assert session.commit_calls == 0
