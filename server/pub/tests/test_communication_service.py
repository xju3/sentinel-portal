from pub.services.sensor.communication_service import SensorCommunicationService


def test_payload_to_event_accepts_normalized_sensor_sn_and_missing_duration():
    assert SensorCommunicationService.payload_to_event(
        {
            "sensor_sn": "STL26SH0001",
            "ts_ms": 1_785_400_000_000,
        }
    ) == {
        "sn": "STL26SH0001",
        "ts_ms": 1_785_400_000_000,
        "duration_ms": 0.0,
    }
