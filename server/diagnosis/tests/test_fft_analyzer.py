from __future__ import annotations

import importlib
import json
from io import BytesIO
from pathlib import Path
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest

DIAGNOSIS_ROOT = Path(__file__).resolve().parents[1]
SERVER_ROOT = Path(__file__).resolve().parents[2]
diagnosis_root_str = str(DIAGNOSIS_ROOT)
server_root_str = str(SERVER_ROOT)
if diagnosis_root_str in sys.path:
    sys.path.remove(diagnosis_root_str)
sys.path.insert(0, diagnosis_root_str)
if server_root_str not in sys.path:
    sys.path.append(server_root_str)
saved_app_modules = {
    module_name: module
    for module_name, module in list(sys.modules.items())
    if module_name == "app" or module_name.startswith("app.")
}
for module_name in saved_app_modules:
    sys.modules.pop(module_name, None)
fft_analyzer_module = importlib.import_module("app.handler.fft_analyzer")
fft_parser_module = importlib.import_module("app.preparation.fft_parser")
context_module = importlib.import_module("app.services.context")
for module_name in list(sys.modules):
    if (module_name == "app" or module_name.startswith("app.")) and module_name not in saved_app_modules:
        sys.modules.pop(module_name, None)
sys.modules.update(saved_app_modules)

FftAnalyzer = fft_analyzer_module.FftAnalyzer
FftData = fft_parser_module.FftData
FftParser = fft_parser_module.FftParser
build_preview_payload = fft_parser_module.build_preview_payload
DeviceContextService = context_module.DeviceContextService
from pub.services.sensor.sensor_task_service import FFT_COLLECTION_ACTION


class FakeExecuteResult:
    def __init__(self, scalar=None):
        self._scalar = scalar

    def scalar_one_or_none(self):
        return self._scalar


class FakeSession:
    def __init__(self, responses, *, get_map=None):
        self._responses = list(responses)
        self._get_map = dict(get_map or {})
        self.added = []
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

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commit_calls += 1

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeMinioClient:
    def __init__(self):
        self.uploads = []

    def put_object(self, **kwargs):
        raw = kwargs["data"].read()
        self.uploads.append(
            SimpleNamespace(
                bucket_name=kwargs["bucket_name"],
                object_name=kwargs["object_name"],
                content_type=kwargs["content_type"],
                payload=json.loads(raw.decode("utf-8")),
            )
        )
        kwargs["data"] = BytesIO(raw)


async def _fake_get_by_device_id(*_args, **_kwargs):
    return {"device_spec": {"rpm": 1500.0}}


@pytest.mark.asyncio
async def test_fft_analyzer_persists_independent_result_and_full_spectrum(monkeypatch):
    task_id = uuid4()
    device_fft_record_id = uuid4()
    task = SimpleNamespace(
        id=task_id,
        action=FFT_COLLECTION_ACTION,
        sn="SN-001",
    )
    device_fft_record = SimpleNamespace(id=device_fft_record_id)
    session = FakeSession(
        [
            FakeExecuteResult(task),
            FakeExecuteResult(None),
            FakeExecuteResult(uuid4()),
            FakeExecuteResult(device_fft_record),
        ],
    )
    monkeypatch.setattr(fft_analyzer_module.db_manager, "SessionLocal", lambda: session)
    monkeypatch.setattr(
        DeviceContextService,
        "get_by_device_id",
        staticmethod(_fake_get_by_device_id),
    )
    fake_minio = FakeMinioClient()
    monkeypatch.setattr(fft_analyzer_module.minio_manager, "get_client", lambda: fake_minio)

    points = 4096
    spectrum_bins = points // 2
    x_axis = [0.0] * spectrum_bins
    x_axis[60] = 9.0
    fft_data = FftData(
        sn_hint="SN-001",
        timestamp_s=1780814415,
        points=points,
        spectrum_bins=spectrum_bins,
        fs=2048.0,
        range_g=8,
        x_axis=x_axis,
        y_axis=[0.0] * spectrum_bins,
        z_axis=[0.0] * spectrum_bins,
    )

    completed = await FftAnalyzer.analyze_and_save(str(task_id), fft_data)

    assert completed is True
    assert session.commit_calls == 1
    assert len(session.added) == 1
    fft_record = session.added[0]
    assert not hasattr(fft_record, "report_id")
    assert fft_record.device_fft_record_id == device_fft_record_id
    assert fft_record.rpm_snapshot == 1500.0
    assert fft_record.rpm_source == "device_spec"
    assert fft_record.spectrum_preview_object_key == f"preview/{task_id}.json"
    assert len(fake_minio.uploads) == 1
    preview = fake_minio.uploads[0]
    assert preview.bucket_name == "fft"
    assert preview.object_name == f"preview/{task_id}.json"
    assert preview.payload["points_preview"] == spectrum_bins
    assert len(preview.payload["x_axis"]) == spectrum_bins


def test_fft_binary_sample_uses_dynamic_half_spectrum():
    sample_path = SERVER_ROOT / "docs" / "fft_binary_data"
    fft_data = FftParser.parse_bytes(
        sample_path.read_bytes(),
        source=str(sample_path),
    )

    assert fft_data is not None
    assert fft_data.timestamp_s == 1782033007
    assert fft_data.points == 8192
    assert fft_data.spectrum_bins == 4096
    assert fft_data.fs == 26667.0
    assert fft_data.range_g == 8
    assert len(fft_data.x_axis) == 4096
    assert len(fft_data.y_axis) == 4096
    assert len(fft_data.z_axis) == 4096

    preview = build_preview_payload(fft_data)
    assert preview["points_preview"] == 4096
    assert preview["freq_hz"][1] == pytest.approx(26667.0 / 8192, abs=1e-6)
