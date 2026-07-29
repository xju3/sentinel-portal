from pub.contract.devices import DeviceInstCreate, DeviceInstResponse
from pub.models.device import DeviceInst


def test_device_inst_create_allows_missing_purchase_date_and_description():
    payload = DeviceInstCreate(
        name="出水阀",
        device_spec_id="fd6ec533-8835-40ae-bd55-ef62b41b5360",
        code="PHM-001",
    )

    assert payload.purchase_date is None
    assert payload.desc is None


def test_device_inst_optional_fields_are_nullable_in_model_and_response():
    assert DeviceInst.__table__.c.purchase_date.nullable is True
    assert DeviceInst.__table__.c.desc.nullable is True
    assert DeviceInstResponse.model_fields["purchase_date"].is_required() is False
    assert DeviceInstResponse.model_fields["desc"].is_required() is False
