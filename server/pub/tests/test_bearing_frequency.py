import pytest
from types import SimpleNamespace
from uuid import uuid4

from pub.services.diagnosis.bearing_frequency import (
    calculate_bearing_frequencies,
    calculate_bearing_orders,
)
from pub.services.diagnosis.diagnosis_context_service import _bearing_binding_context


def test_calculate_bearing_frequencies_uses_local_shaft_speed_ratio():
    result = calculate_bearing_frequencies(
        rpm=1800,
        rolling_element_count=8,
        rolling_element_diameter_mm=10,
        pitch_diameter_mm=50,
        contact_angle_deg=0,
        shaft_speed_ratio=0.2,
    )

    assert result["shaft_speed_ratio"] == pytest.approx(0.2)
    assert result["shaft_rpm"] == pytest.approx(360)
    assert result["shaft_hz"] == pytest.approx(6)
    assert result["BPFO"] == pytest.approx(19.2)
    assert result["BPFI"] == pytest.approx(28.8)
    assert result["BSF"] == pytest.approx(14.4)
    assert result["FTF"] == pytest.approx(2.4)


def test_calculate_bearing_orders_do_not_depend_on_device_rpm():
    result = calculate_bearing_orders(
        rolling_element_count=8,
        rolling_element_diameter_mm=10,
        pitch_diameter_mm=50,
        contact_angle_deg=0,
    )

    assert result == pytest.approx(
        {"BPFO": 3.2, "BPFI": 4.8, "BSF": 2.4, "FTF": 0.4}
    )


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"rpm": 0}, "rpm must be greater than zero"),
        (
            {"rolling_element_count": 7.5},
            "rolling_element_count must be a positive integer",
        ),
        (
            {"rolling_element_diameter_mm": 50},
            "rolling_element_diameter_mm must be smaller",
        ),
        ({"contact_angle_deg": 90}, "contact_angle_deg must be in the range"),
        ({"shaft_speed_ratio": 0}, "shaft_speed_ratio must be greater than zero"),
    ],
)
def test_calculate_bearing_frequencies_rejects_incomplete_or_invalid_geometry(
    override,
    message,
):
    values = {
        "rpm": 1800,
        "rolling_element_count": 8,
        "rolling_element_diameter_mm": 10,
        "pitch_diameter_mm": 50,
        "contact_angle_deg": 0,
        "shaft_speed_ratio": 1,
    }
    values.update(override)

    with pytest.raises(ValueError, match=message):
        calculate_bearing_frequencies(**values)


def test_sn_context_binding_contains_nested_model_and_frequency_reference():
    spec_id = uuid4()
    bearing_id = uuid4()
    binding = SimpleNamespace(
        id=uuid4(),
        device_spec_id=spec_id,
        bearing_id=bearing_id,
        location_id=uuid4(),
        shaft_speed_ratio=0.2,
        enabled=True,
    )
    bearing = SimpleNamespace(
        id=bearing_id,
        tenant_id=uuid4(),
        brand="SKF",
        model="6205",
        bearing_type="deep_groove_ball",
        rolling_element_count=8,
        rolling_element_diameter_mm=10.0,
        pitch_diameter_mm=50.0,
        contact_angle_deg=0.0,
        description=None,
        active=True,
    )

    result = _bearing_binding_context(binding, bearing, rpm=1800)

    assert result["location_id"] == binding.location_id
    assert result["shaft_speed_ratio"] == pytest.approx(0.2)
    assert result["bearing"]["model"] == "6205"
    assert result["frequency_reference_hz"]["BPFO"] == pytest.approx(19.2)
    assert result["frequency_validation_error"] is None
