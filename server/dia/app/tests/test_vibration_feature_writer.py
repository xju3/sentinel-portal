import json
from pathlib import Path

from server.dia.app.clients.influxdb_client import build_vibration_feature_lines


def test_build_vibration_feature_lines_flattens_axis_features():
    payload_path = Path(__file__).resolve().parents[4] / "docs" / "result.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))

    lines = build_vibration_feature_lines(payload)
    report_id = payload["report_id"]

    assert len(lines) == 3
    assert all(line.startswith("vibration_feature,") for line in lines)
    assert f"report_id={report_id},sn=STL26SH0001,axis=X,sample_type=normal" in lines[0]
    assert "temperature_c=2" in lines[0]
    assert "rms_acc_g=0.011" in lines[0]
    assert "spectral_centroid_hz=2438.6" in lines[0]
    assert "band_0_100=0.027" in lines[0]
    assert "band_2000_5000=0.586" in lines[0]
    assert "peak1_freq_hz=4492.2" in lines[0]
    assert "peak1_amp_g=0.0008" in lines[0]
    assert "peak4_freq_hz=4049.5" in lines[0]
    assert "peak5_freq_hz" not in lines[0]
    assert lines[0].endswith("1780814415097000000")


def test_build_vibration_feature_lines_repeats_temperature_per_axis():
    payload_path = Path(__file__).resolve().parents[4] / "docs" / "result.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))

    lines = build_vibration_feature_lines(payload)
    report_id = payload["report_id"]

    assert all("temperature_c=2" in line for line in lines)
    assert all(f"report_id={report_id}" in line for line in lines)
    assert "axis=X" in lines[0]
    assert "axis=Y" in lines[1]
    assert "axis=Z" in lines[2]
