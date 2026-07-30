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
build_device_bearing_context = context_module._bearing_binding_context
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
    x_axis[50] = 9.0
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
    assert fft_record.conclusion == "Mass Unbalance / Looseness (1X)"
    assert fft_record.details["analysis_mode"] == "Configured-RPM Magnitude Spectrum Screening"
    assert fft_record.details["bearing_frequency_inputs_available"] is False
    assert fft_record.details["analysis_limitations"][1] == (
        "No envelope/demodulation analysis is performed, so bearing defect frequencies cannot be confirmed."
    )
    assert fft_record.details["plot_metadata"]["reference_markers_hz"] == {
        "1x": 25.0,
        "2x": 50.0,
        "3x": 75.0,
    }
    assert fft_record.spectrum_preview_object_key == f"preview/{task_id}.json"
    assert len(fake_minio.uploads) == 1
    preview = fake_minio.uploads[0]
    assert preview.bucket_name == "fft"
    assert preview.object_name == f"preview/{task_id}.json"
    assert preview.payload["points_preview"] == spectrum_bins
    assert len(preview.payload["x_axis"]) == spectrum_bins
    assert preview.payload["analysis"]["mode"] == "Configured-RPM Magnitude Spectrum Screening"
    assert preview.payload["analysis"]["envelope_analysis_performed"] is False
    assert preview.payload["analysis"]["dominant_peak"] == {
        "axis": "X",
        "frequency_hz": 25.0,
        "amplitude_g": 9.0,
        "ratio_to_1x": 1.0,
    }


@pytest.mark.asyncio
async def test_fft_analyzer_uses_generic_high_frequency_screening_without_bearing_claim(monkeypatch):
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
    x_axis[200] = 7.5
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
    fft_record = session.added[0]
    assert fft_record.conclusion == "High Frequency Excitation (>3X)"
    assert "Bearing" not in fft_record.conclusion
    assert fft_record.details["dominant_ratio_to_1x"] == pytest.approx(4.0, abs=1e-6)
    assert fft_record.details["plot_metadata"]["bearing_frequency_inputs_available"] is False
    assert fft_record.details["plot_metadata"]["envelope_analysis_performed"] is False
    preview = fake_minio.uploads[0]
    assert preview.payload["analysis"]["reference_markers_hz"]["3x"] == 75.0
    assert preview.payload["analysis"]["limitations"][3] == (
        "Missing bearing geometry/fault-frequency parameters prevent BPFI/BPFO/BSF matching."
    )


@pytest.mark.asyncio
async def test_fft_analyzer_saves_generic_spectrum_when_rpm_is_missing(monkeypatch):
    task_id = uuid4()
    device_fft_record_id = uuid4()
    session = FakeSession(
        [
            FakeExecuteResult(
                SimpleNamespace(id=task_id, action=FFT_COLLECTION_ACTION, sn="SN-001")
            ),
            FakeExecuteResult(None),
            FakeExecuteResult(uuid4()),
            FakeExecuteResult(SimpleNamespace(id=device_fft_record_id)),
        ],
    )
    monkeypatch.setattr(fft_analyzer_module.db_manager, "SessionLocal", lambda: session)

    async def _context_without_rpm(*_args, **_kwargs):
        return {"device_spec": {"rpm": 0}, "bearing_bindings": []}

    monkeypatch.setattr(
        DeviceContextService,
        "get_by_device_id",
        staticmethod(_context_without_rpm),
    )
    fake_minio = FakeMinioClient()
    monkeypatch.setattr(fft_analyzer_module.minio_manager, "get_client", lambda: fake_minio)

    points = 128
    x_axis = [0.0] * (points // 2)
    x_axis[10] = 3.0
    completed = await FftAnalyzer.analyze_and_save(
        str(task_id),
        FftData(
            sn_hint="SN-001",
            timestamp_s=1780814415,
            points=points,
            spectrum_bins=points // 2,
            fs=128.0,
            range_g=8,
            x_axis=x_axis,
            y_axis=[0.0] * (points // 2),
            z_axis=[0.0] * (points // 2),
        ),
    )

    assert completed is True
    fft_record = session.added[0]
    assert fft_record.conclusion == "Generic Spectrum Observation"
    assert fft_record.rpm_snapshot is None
    assert fft_record.base_frequency_hz is None
    assert fft_record.details["analysis_mode"] == "Generic Magnitude Spectrum Screening"
    assert fft_record.details["plot_metadata"]["reference_markers_hz"] == {}
    assert "Device RPM is not configured" in fft_record.details["analysis_limitations"][2]


def test_fft_plot_metadata_exposes_bearing_markers_as_non_diagnostic_hints():
    metadata = FftAnalyzer._build_plot_metadata(
        analysis_limitations=[],
        max_amp=4.2,
        max_axis="Y",
        max_freq=96.2,
        base_freq=30.0,
        dominant_ratio=96.2 / 30.0,
        analysis_mode=FftAnalyzer._ANALYSIS_MODE,
        bearing_references=[
            {
                "binding_id": "binding-1",
                "location_id": str(uuid4()),
                "bearing": {"id": "bearing-1", "brand": "SKF", "model": "6205"},
                "frequencies_hz": {
                    "BPFO": 96.0,
                    "BPFI": 144.0,
                    "BSF": 72.0,
                    "FTF": 12.0,
                },
                "bsf_definition": (
                    "Rolling-element spin frequency; this marker is BSF, not 2x BSF."
                ),
            }
        ],
        resolution_hz=1.0,
    )

    assert metadata["bearing_reference_markers"][0]["frequencies_hz"]["BPFO"] == 96.0
    assert metadata["bearing_reference_markers"][0]["bsf_definition"].endswith(
        "not 2x BSF."
    )
    assert metadata["bearing_match_hints"][0]["frequency_name"] == "BPFO"
    assert "envelope analysis is required" in metadata["bearing_match_hints"][0][
        "interpretation"
    ]
    assert metadata["envelope_analysis_performed"] is False


def test_device_context_binding_rejects_incomplete_bearing_parameters():
    binding = SimpleNamespace(
        id=uuid4(),
        device_spec_id=uuid4(),
        bearing_id=uuid4(),
        location_id=uuid4(),
        shaft_speed_ratio=1.0,
        enabled=True,
    )
    bearing = SimpleNamespace(
        id=binding.bearing_id,
        tenant_id=uuid4(),
        brand="Unknown",
        model="Incomplete",
        bearing_type=None,
        rolling_element_count=8,
        rolling_element_diameter_mm=0,
        pitch_diameter_mm=50,
        contact_angle_deg=0,
        description=None,
        active=True,
    )

    result = build_device_bearing_context(binding, bearing, rpm=1500)

    assert result["frequency_reference_hz"] is None
    assert result["frequency_validation_error"] == (
        "rolling_element_diameter_mm must be greater than zero"
    )


@pytest.mark.asyncio
async def test_device_context_cache_invalidation_deletes_unique_device_keys(monkeypatch):
    class FakeRedis:
        def __init__(self):
            self.deleted = None

        def delete(self, *keys):
            self.deleted = keys

    client = FakeRedis()
    monkeypatch.setattr(context_module, "_get_redis_client", lambda: client)

    await DeviceContextService.invalidate_by_device_ids(["device-2", "device-1", "device-2"])

    assert client.deleted == (
        "dia:device_context:device-1",
        "dia:device_context:device-2",
    )


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
