from pub.models.sensor import CommunicationRecord
from pub.services.communication_service import SensorCommunicationService


def test_communication_service_uses_current_record_model():
    assert SensorCommunicationService.record.__annotations__["return"] is CommunicationRecord
