"""Server-owned diagnosis from compact device-computed bearing evidence."""

from __future__ import annotations

from typing import Any

from app.config import settings
from pub.models.report import BearingFeatures

FAULT_CODES = ("bpfo", "bpfi", "bsf", "ftf")
AXIS_METRIC_IDS = {"X": 1, "Y": 2, "Z": 3}


class BearingDiagnosis:
    """Validate frequency candidates and assign the server health level."""

    @staticmethod
    def analyze(
        features: BearingFeatures | None,
        context: dict[str, Any],
        *,
        location_id: str,
        fs_hz: int | None,
        points: int | None,
    ) -> list[dict[str, Any]]:
        if features is None:
            return []

        binding = BearingDiagnosis._binding_for_location(context, location_id)
        references = (binding or {}).get("frequency_reference_hz") or {}
        if not references:
            return []

        resolution_hz = (
            float(fs_hz) / float(points)
            if fs_hz and points and fs_hz > 0 and points > 0
            else 0.0
        )
        nyquist_hz = float(fs_hz) / 2.0 if fs_hz and fs_hz > 0 else None
        results: list[dict[str, Any]] = []
        for axis in AXIS_METRIC_IDS:
            axis_features = getattr(features, axis)
            if axis_features.status != 0:
                continue
            for code in FAULT_CODES:
                base_hz = references.get(code.upper())
                if base_hz is None:
                    continue
                candidates = getattr(axis_features.fault_candidates, code)
                result = BearingDiagnosis._analyze_fault(
                    code=code,
                    axis=axis,
                    base_hz=float(base_hz),
                    resolution_hz=resolution_hz,
                    nyquist_hz=nyquist_hz,
                    envelope_kurtosis=axis_features.envelope_kurtosis,
                    candidates=candidates,
                    binding=binding,
                )
                if result["level"] > 0:
                    results.append(result)
        return results

    @staticmethod
    def _binding_for_location(
        context: dict[str, Any],
        location_id: str,
    ) -> dict[str, Any] | None:
        target = str(location_id)
        for binding in context.get("bearing_bindings") or []:
            if str(binding.get("location_id")) == target:
                return binding
        return None

    @staticmethod
    def _analyze_fault(
        *,
        code: str,
        axis: str,
        base_hz: float,
        resolution_hz: float,
        nyquist_hz: float | None,
        envelope_kurtosis: float | None,
        candidates: list[Any],
        binding: dict[str, Any],
    ) -> dict[str, Any]:
        matched_by_harmonic: dict[int, dict[str, Any]] = {}
        rejected: list[dict[str, Any]] = []
        for candidate in candidates:
            expected_hz = base_hz * candidate.harmonic
            if (
                nyquist_hz is not None
                and (
                    expected_hz > nyquist_hz
                    or candidate.observed_hz > nyquist_hz
                )
            ):
                continue
            tolerance_hz = max(
                expected_hz * settings.bearing_frequency_tolerance_ratio,
                resolution_hz * settings.bearing_frequency_tolerance_bins,
            )
            deviation_hz = candidate.observed_hz - expected_hz
            evidence = {
                "harmonic": candidate.harmonic,
                "expected_hz": expected_hz,
                "observed_hz": candidate.observed_hz,
                "deviation_hz": deviation_hz,
                "tolerance_hz": tolerance_hz,
                "snr_db": candidate.snr_db,
            }
            if abs(deviation_hz) > tolerance_hz:
                rejected.append(evidence)
                continue
            current = matched_by_harmonic.get(candidate.harmonic)
            if current is None or candidate.snr_db > current["snr_db"]:
                matched_by_harmonic[candidate.harmonic] = evidence

        matched = [
            matched_by_harmonic[harmonic]
            for harmonic in sorted(matched_by_harmonic)
        ]
        best_snr_db = max(
            (candidate["snr_db"] for candidate in matched),
            default=float("-inf"),
        )
        level = BearingDiagnosis._level_from_snr(best_snr_db)
        bearing = binding.get("bearing") or {}
        evidence = {
            "schema_version": 1,
            "axis": axis,
            "fault_code": code,
            "bearing_id": binding.get("bearing_id"),
            "bearing_model": bearing.get("model"),
            "base_frequency_hz": base_hz,
            "frequency_resolution_hz": resolution_hz,
            "envelope_kurtosis": envelope_kurtosis,
            "matched_harmonic_count": len(matched),
            "best_snr_db": None if best_snr_db == float("-inf") else best_snr_db,
            "matched_candidates": matched,
            "rejected_candidates": rejected,
            "level_thresholds_db": {
                "attention": settings.bearing_attention_snr_db,
                "abnormal": settings.bearing_abnormal_snr_db,
                "warning": settings.bearing_warning_snr_db,
                "critical": settings.bearing_critical_snr_db,
            },
            "checks": [
                {
                    "code": (
                        f"bearing.{code}.{axis.lower()}."
                        f"h{candidate['harmonic']}"
                    ),
                    "label": (
                        f"{axis}轴 {code.upper()} "
                        f"{candidate['harmonic']}倍频"
                    ),
                    "axis": axis,
                    "observed": candidate["snr_db"],
                    "operator": ">=",
                    "threshold": settings.bearing_attention_snr_db,
                    "unit": "dB",
                    "triggered": candidate["snr_db"]
                    >= settings.bearing_attention_snr_db,
                    "expected_hz": candidate["expected_hz"],
                    "observed_hz": candidate["observed_hz"],
                    "deviation_hz": candidate["deviation_hz"],
                }
                for candidate in matched
            ],
        }
        return {
            "fault_code": code,
            "axis": axis,
            "metric_id": AXIS_METRIC_IDS[axis],
            "level": level,
            "description": (
                f"{axis}轴检测到{code.upper()}特征，"
                f"最高信噪比{best_snr_db:.1f}dB"
                if level > 0
                else None
            ),
            "evidence": evidence,
        }

    @staticmethod
    def _level_from_snr(snr_db: float) -> int:
        if snr_db >= settings.bearing_critical_snr_db:
            return 4
        if snr_db >= settings.bearing_warning_snr_db:
            return 3
        if snr_db >= settings.bearing_abnormal_snr_db:
            return 2
        if snr_db >= settings.bearing_attention_snr_db:
            return 1
        return 0

    @staticmethod
    def should_notify(
        current_level: int,
        previous_levels: list[int],
        *,
        confirmation_count: int,
        immediate_level: int,
    ) -> bool:
        """Separate per-cycle diagnosis from customer-notification confirmation."""
        if current_level >= immediate_level:
            return True
        required_previous = max(0, confirmation_count - 1)
        return (
            current_level > 0
            and sum(level > 0 for level in previous_levels)
            >= required_previous
        )
