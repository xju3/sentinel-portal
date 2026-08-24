from types import SimpleNamespace

from app.handler import bearing as bearing_module
from app.handler.bearing import BearingDiagnosis
from pub.models.report import BearingFeatures


def _features(snr_db: float = 10.0) -> BearingFeatures:
    return BearingFeatures.model_validate(
        {
            "X": {
                "status": 0,
                "envelope_kurtosis": 6.2,
                "fault_candidates": {
                    "bpfo": [
                        {
                            "harmonic": 1,
                            "observed_hz": 20.1,
                            "snr_db": snr_db,
                        }
                    ]
                },
            },
            "Y": {
                "status": 0,
                "envelope_kurtosis": 3.0,
                "fault_candidates": {},
            },
            "Z": {
                "status": 1,
                "envelope_kurtosis": None,
                "fault_candidates": {},
            },
        }
    )


def _context() -> dict:
    return {
        "bearing_bindings": [
            {
                "bearing_id": "bearing-1",
                "location_id": "location-1",
                "bearing": {"model": "6205"},
                "frequency_reference_hz": {
                    "BPFO": 20.0,
                    "BPFI": 30.0,
                    "BSF": 12.0,
                    "FTF": 2.0,
                },
            }
        ]
    }


def test_bearing_diagnosis_uses_server_binding_and_assigns_level(monkeypatch):
    monkeypatch.setattr(
        bearing_module,
        "settings",
        SimpleNamespace(
            bearing_frequency_tolerance_ratio=0.02,
            bearing_frequency_tolerance_bins=2.0,
            bearing_attention_snr_db=6.0,
            bearing_abnormal_snr_db=10.0,
            bearing_warning_snr_db=15.0,
            bearing_critical_snr_db=20.0,
        ),
    )

    results = BearingDiagnosis.analyze(
        _features(),
        _context(),
        location_id="location-1",
        fs_hz=1000,
        points=1000,
    )

    assert len(results) == 1
    assert results[0]["fault_code"] == "bpfo"
    assert results[0]["axis"] == "X"
    assert results[0]["level"] == 2
    assert results[0]["evidence"]["bearing_id"] == "bearing-1"
    assert results[0]["evidence"]["matched_candidates"][0]["expected_hz"] == 20.0


def test_bearing_diagnosis_ignores_wrong_location_and_insufficient_axis():
    assert BearingDiagnosis.analyze(
        _features(),
        _context(),
        location_id="another-location",
        fs_hz=1000,
        points=1000,
    ) == []
