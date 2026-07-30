from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request
from starlette.datastructures import Headers

from app.services.wx_diagnosis_access_service import (
    WxDiagnosisAccessService,
    WxDiagnosisCookieClaims,
)
from pub.models.diagnosis import (
    DiagnosisNotificationDeliveryStatus,
)


class FakeSession:
    def __init__(self, mapping):
        self.mapping = mapping

    async def get(self, model, key):
        return self.mapping.get((model.__name__, key))


def _request(path: str = "/api/v1/wx/diagnosis/entry") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": Headers({}).raw,
        "query_string": b"",
        "server": ("testserver", 80),
        "scheme": "http",
        "root_path": "",
        "client": ("127.0.0.1", 12345),
    }
    return Request(scope)


def test_signed_state_round_trip():
    delivery_id = uuid4()
    report_id = uuid4()

    token = WxDiagnosisAccessService.create_signed_state(
        delivery_id=delivery_id,
        report_id=report_id,
        fault_type="vibration",
        nonce="fixed-nonce",
        expires_in_seconds=60,
    )

    state = WxDiagnosisAccessService.decode_signed_state(token)

    assert state.delivery_id == delivery_id
    assert state.report_id == report_id
    assert state.fault_type == "vibration"
    assert state.nonce == "fixed-nonce"


@pytest.mark.asyncio
async def test_authorize_callback_issues_delivery_scoped_cookie(monkeypatch):
    delivery_id = uuid4()
    report_id = uuid4()
    employee_id = uuid4()
    state = WxDiagnosisAccessService.create_signed_state(
        delivery_id=delivery_id,
        report_id=report_id,
        fault_type="temperature",
        nonce="nonce-1",
        expires_in_seconds=60,
    )
    delivery = SimpleNamespace(
        id=delivery_id,
        report_id=report_id,
        employee_id=employee_id,
        fault_type="temperature",
        status=DiagnosisNotificationDeliveryStatus.SENT,
        recipient_wx_user_id="wx-user-1",
        wx_user_id="wx-user-1",
    )
    employee = SimpleNamespace(
        id=employee_id,
        active=True,
        wx_user_id="wx-user-1",
    )
    session = FakeSession(
        {
            ("DiagnosisNotificationDelivery", delivery_id): delivery,
            ("Employee", employee_id): employee,
        }
    )
    monkeypatch.setattr(
        WxDiagnosisAccessService,
        "exchange_code_for_openid",
        staticmethod(lambda _code: _async_value("wx-user-1")),
    )

    result = await WxDiagnosisAccessService.authorize_callback(
        session=session,
        request=_request("/api/v1/wx/diagnosis/callback"),
        code="wechat-code",
        state_token=state,
    )

    claims = WxDiagnosisAccessService.decode_cookie(result.cookie_value)
    assert claims.report_id == report_id
    assert claims.delivery_id == delivery_id
    assert claims.wx_user_id == "wx-user-1"
    assert result.redirect_url.endswith(f"/wx/diagnosis/{report_id}")


@pytest.mark.asyncio
async def test_authorize_report_access_rejects_rebound_employee():
    delivery_id = uuid4()
    report_id = uuid4()
    employee_id = uuid4()
    claims = WxDiagnosisCookieClaims(
        delivery_id=delivery_id,
        report_id=report_id,
        employee_id=employee_id,
        wx_user_id="wx-user-old",
        fault_type="vibration",
        iat=1,
        exp=4_102_444_800,
    )
    delivery = SimpleNamespace(
        id=delivery_id,
        report_id=report_id,
        employee_id=employee_id,
        fault_type="vibration",
        status=DiagnosisNotificationDeliveryStatus.SENT,
        recipient_wx_user_id="wx-user-old",
        wx_user_id="wx-user-old",
    )
    employee = SimpleNamespace(
        id=employee_id,
        active=True,
        wx_user_id="wx-user-new",
    )
    session = FakeSession(
        {
            ("DiagnosisNotificationDelivery", delivery_id): delivery,
            ("Employee", employee_id): employee,
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        await WxDiagnosisAccessService.authorize_report_access(
            session=session,
            report_id=report_id,
            claims=claims,
        )

    assert exc_info.value.status_code == 403
    assert "binding has changed" in exc_info.value.detail


def _async_value(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner()
