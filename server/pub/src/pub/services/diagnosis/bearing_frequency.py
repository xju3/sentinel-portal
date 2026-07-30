"""Pure bearing characteristic-order and frequency calculations.

The formulas assume the common installation where the inner race follows the
local shaft and the outer race is fixed.  ``shaft_speed_ratio`` maps the device
specification RPM to the local shaft RPM.
"""

from __future__ import annotations

import math
from typing import Any


def calculate_bearing_frequencies(
    *,
    rpm: Any,
    rolling_element_count: Any,
    rolling_element_diameter_mm: Any,
    pitch_diameter_mm: Any,
    contact_angle_deg: Any,
    shaft_speed_ratio: Any = 1.0,
) -> dict[str, float]:
    """Return local-shaft BPFO/BPFI/BSF/FTF frequencies.

    ``BSF`` is the rolling-element spin frequency, not the sometimes plotted
    ``2 * BSF`` ball-defect impact line.
    """
    base_rpm = _positive_float("rpm", rpm)
    speed_ratio = _positive_float("shaft_speed_ratio", shaft_speed_ratio)
    shaft_hz = base_rpm * speed_ratio / 60.0
    orders = calculate_bearing_orders(
        rolling_element_count=rolling_element_count,
        rolling_element_diameter_mm=rolling_element_diameter_mm,
        pitch_diameter_mm=pitch_diameter_mm,
        contact_angle_deg=contact_angle_deg,
    )
    return {
        "shaft_speed_ratio": speed_ratio,
        "shaft_rpm": base_rpm * speed_ratio,
        "shaft_hz": shaft_hz,
        "BPFO": orders["BPFO"] * shaft_hz,
        "BPFI": orders["BPFI"] * shaft_hz,
        "BSF": orders["BSF"] * shaft_hz,
        "FTF": orders["FTF"] * shaft_hz,
    }


def calculate_bearing_orders(
    *,
    rolling_element_count: Any,
    rolling_element_diameter_mm: Any,
    pitch_diameter_mm: Any,
    contact_angle_deg: Any,
) -> dict[str, float]:
    """Return BPFO/BPFI/BSF/FTF orders relative to the local shaft."""
    element_count = _positive_int("rolling_element_count", rolling_element_count)
    element_diameter = _positive_float(
        "rolling_element_diameter_mm", rolling_element_diameter_mm
    )
    pitch_diameter = _positive_float("pitch_diameter_mm", pitch_diameter_mm)
    if element_diameter >= pitch_diameter:
        raise ValueError(
            "rolling_element_diameter_mm must be smaller than pitch_diameter_mm"
        )

    contact_angle = _finite_float("contact_angle_deg", contact_angle_deg)
    if not 0.0 <= contact_angle < 90.0:
        raise ValueError("contact_angle_deg must be in the range [0, 90)")

    diameter_ratio_cos = (
        element_diameter
        / pitch_diameter
        * math.cos(math.radians(contact_angle))
    )
    if not 0.0 <= diameter_ratio_cos < 1.0:
        raise ValueError("bearing geometry produces an invalid diameter ratio")

    bpfo_order = element_count / 2.0 * (1.0 - diameter_ratio_cos)
    bpfi_order = element_count / 2.0 * (1.0 + diameter_ratio_cos)
    bsf_order = (
        pitch_diameter
        / (2.0 * element_diameter)
        * (1.0 - diameter_ratio_cos**2)
    )
    ftf_order = 0.5 * (1.0 - diameter_ratio_cos)

    return {
        "BPFO": bpfo_order,
        "BPFI": bpfi_order,
        "BSF": bsf_order,
        "FTF": ftf_order,
    }


def _finite_float(name: str, value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


def _positive_float(name: str, value: Any) -> float:
    result = _finite_float(name, value)
    if result <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return result


def _positive_int(name: str, value: Any) -> int:
    number = _finite_float(name, value)
    if number <= 0 or not number.is_integer():
        raise ValueError(f"{name} must be a positive integer")
    return int(number)
