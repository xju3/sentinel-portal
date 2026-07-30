from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.clients import fft_stream_worker


@pytest.mark.asyncio
async def test_fft_stream_acknowledges_completed_diagnosis(monkeypatch):
    task_id = uuid4()
    client = Mock()
    monkeypatch.setattr(
        fft_stream_worker,
        "process_fft_metadata_background",
        AsyncMock(return_value=True),
    )

    await fft_stream_worker._process_message(
        client=client,
        worker_id="fft-worker",
        message_id="1-0",
        fields={"task_id": str(task_id)},
    )

    client.xack.assert_called_once_with(
        "stream:diagnosis:fft",
        "diagnosis:fft:workers",
        "1-0",
    )


@pytest.mark.asyncio
async def test_fft_stream_leaves_incomplete_diagnosis_pending(monkeypatch):
    client = Mock()
    monkeypatch.setattr(
        fft_stream_worker,
        "process_fft_metadata_background",
        AsyncMock(return_value=False),
    )

    await fft_stream_worker._process_message(
        client=client,
        worker_id="fft-worker",
        message_id="2-0",
        fields={"task_id": str(uuid4())},
    )

    client.xack.assert_not_called()
