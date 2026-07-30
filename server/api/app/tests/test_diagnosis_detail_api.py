from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.main import app
from app.routers import diagnosis_detail as diagnosis_detail_router
from app.routers import wx as wx_router
from app.services.wx_diagnosis_access_service import WxDiagnosisCookieClaims
from app.utils.auth import get_current_account


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


async def _fake_session_dependency():
    yield object()


@pytest.mark.asyncio
async def test_portal_detail_route_uses_tenant_scoped_service(monkeypatch):
    report_id = uuid4()
    tenant_id = uuid4()
    captured: dict[str, object] = {}

    async def fake_get_portal_detail(*, session, report_id, tenant_id):
        captured["session"] = session
        captured["report_id"] = report_id
        captured["tenant_id"] = tenant_id
        return {"report": {"report_id": str(report_id)}}

    monkeypatch.setattr(
        diagnosis_detail_router.DiagnosisReportDetailService,
        "get_portal_detail",
        fake_get_portal_detail,
    )
    app.dependency_overrides[get_current_account] = lambda: SimpleNamespace(
        tenant_id=tenant_id
    )
    app.dependency_overrides[diagnosis_detail_router.get_session] = (
        _fake_session_dependency
    )

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(f"/api/v1/diagnosis/reports/{report_id}/detail")

    assert response.status_code == 200
    assert response.json()["data"]["report"]["report_id"] == str(report_id)
    assert captured["report_id"] == report_id
    assert captured["tenant_id"] == tenant_id


@pytest.mark.asyncio
async def test_wx_diagnosis_detail_route_uses_cookie_claims(monkeypatch):
    report_id = uuid4()
    delivery_id = uuid4()
    employee_id = uuid4()
    claims = WxDiagnosisCookieClaims(
        delivery_id=delivery_id,
        report_id=report_id,
        employee_id=employee_id,
        wx_user_id="wx-openid-1",
        fault_type="temperature",
        iat=1,
        exp=4_102_444_800,
    )

    app.dependency_overrides[diagnosis_detail_router.get_wx_diagnosis_claims] = (
        lambda: claims
    )
    authorize_access = AsyncMock(return_value=None)
    monkeypatch.setattr(
        diagnosis_detail_router.WxDiagnosisAccessService,
        "authorize_report_access",
        authorize_access,
    )
    get_report_detail = AsyncMock(
        return_value={"report": {"report_id": str(report_id)}}
    )
    monkeypatch.setattr(
        diagnosis_detail_router.DiagnosisReportDetailService,
        "get_report_detail",
        get_report_detail,
    )
    app.dependency_overrides[diagnosis_detail_router.get_session] = (
        _fake_session_dependency
    )

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(f"/api/v1/wx/diagnosis/reports/{report_id}")

    assert response.status_code == 200
    authorize_access.assert_awaited_once()
    assert get_report_detail.await_args.kwargs["fault_type"] == "temperature"
    assert response.json()["data"]["report"]["report_id"] == str(report_id)


@pytest.mark.asyncio
async def test_wx_callback_sets_scoped_cookie_and_redirects(monkeypatch):
    report_id = uuid4()

    monkeypatch.setattr(
        wx_router.WxDiagnosisAccessService,
        "authorize_callback",
        AsyncMock(
            return_value=SimpleNamespace(
                redirect_url=f"https://portal.example.test/wx/diagnosis/{report_id}",
                cookie_value="signed-cookie",
                cookie_max_age=900,
                cookie_path="/api/v1/wx/diagnosis",
            )
        ),
    )
    app.dependency_overrides[wx_router.get_session] = _fake_session_dependency

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/wx/diagnosis/callback",
            params={"code": "wechat-code", "state": "signed-state"},
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert response.headers["location"] == (
        f"https://portal.example.test/wx/diagnosis/{report_id}"
    )
    cookie = response.headers["set-cookie"]
    assert "wx_diagnosis_access=signed-cookie" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Path=/api/v1/wx/diagnosis" in cookie


@pytest.mark.asyncio
async def test_wx_entry_derives_signed_state_from_delivery(monkeypatch):
    delivery_id = uuid4()
    report_id = uuid4()
    delivery = SimpleNamespace(
        id=delivery_id,
        report_id=report_id,
        fault_type="temperature",
    )

    class EntrySession:
        async def get(self, _model, key):
            return delivery if key == delivery_id else None

    monkeypatch.setattr(
        wx_router.WxDiagnosisAccessService,
        "create_signed_state",
        lambda **kwargs: "signed-state",
    )
    monkeypatch.setattr(
        wx_router.WxDiagnosisAccessService,
        "build_oauth_authorize_url",
        lambda request, state_token: (
            f"https://open.weixin.qq.com/connect/oauth2/authorize?state={state_token}"
        ),
    )

    response = await wx_router.wx_diagnosis_entry(
        request=SimpleNamespace(),
        delivery_id=delivery_id,
        session=EntrySession(),
    )

    assert response.status_code == 302
    assert response.headers["location"].endswith("state=signed-state")
