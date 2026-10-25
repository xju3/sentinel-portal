from __future__ import annotations

import importlib
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
context_module = importlib.import_module("app.services.context")
for module_name in list(sys.modules):
    if (module_name == "app" or module_name.startswith("app.")) and module_name not in saved_app_modules:
        sys.modules.pop(module_name, None)
sys.modules.update(saved_app_modules)

DeviceContextService = context_module.DeviceContextService
build_device_bearing_context = context_module._bearing_binding_context


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
