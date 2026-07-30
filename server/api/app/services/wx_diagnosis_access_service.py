from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

import httpx
from fastapi import HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from pub.models.diagnosis import (
    DiagnosisNotificationDelivery,
    DiagnosisNotificationDeliveryStatus,
)
from pub.models.org import Employee


class WxDiagnosisState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    delivery_id: UUID
    report_id: UUID
    fault_type: str | None = None
    nonce: str
    exp: int

    @field_validator("nonce")
    @classmethod
    def _validate_nonce(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("nonce must not be empty")
        return value


class WxDiagnosisCookieClaims(BaseModel):
    model_config = ConfigDict(extra="forbid")

    delivery_id: UUID
    report_id: UUID
    employee_id: UUID
    wx_user_id: str
    fault_type: str | None = None
    iat: int
    exp: int

    @field_validator("wx_user_id")
    @classmethod
    def _validate_wx_user_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("wx_user_id must not be empty")
        return value


@dataclass(slots=True)
class WxDiagnosisCallbackResult:
    redirect_url: str
    cookie_value: str
    cookie_max_age: int
    cookie_path: str


class WxDiagnosisAccessService:
    """Signed WeChat delivery-scope authorization for diagnosis detail pages."""

    @staticmethod
    def create_signed_state(
        *,
        delivery_id: UUID,
        report_id: UUID,
        fault_type: str | None,
        nonce: str | None = None,
        expires_in_seconds: int | None = None,
    ) -> str:
        ttl = expires_in_seconds or settings.wx_diagnosis_state_ttl_seconds
        payload = WxDiagnosisState(
            delivery_id=delivery_id,
            report_id=report_id,
            fault_type=fault_type,
            nonce=nonce or secrets.token_urlsafe(12),
            exp=_now_ts() + ttl,
        )
        return _sign_payload(payload.model_dump(mode="json"))

    @staticmethod
    def decode_signed_state(token: str) -> WxDiagnosisState:
        return WxDiagnosisState.model_validate(_verify_payload(token))

    @staticmethod
    def create_cookie(claims: WxDiagnosisCookieClaims) -> str:
        return _sign_payload(claims.model_dump(mode="json"))

    @staticmethod
    def decode_cookie(token: str) -> WxDiagnosisCookieClaims:
        return WxDiagnosisCookieClaims.model_validate(_verify_payload(token))

    @staticmethod
    def build_oauth_authorize_url(request: Request, state_token: str) -> str:
        callback_url = settings.wx_diagnosis_callback_url or str(
            request.url_for("wx_diagnosis_callback")
        )
        query = urlencode(
            {
                "appid": settings.wx_app_id,
                "redirect_uri": callback_url,
                "response_type": "code",
                "scope": settings.wx_diagnosis_oauth_scope,
                "state": state_token,
            }
        )
        return f"{settings.wx_oauth_authorize_url}?{query}#wechat_redirect"

    @staticmethod
    async def exchange_code_for_openid(code: str) -> str:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.wx_oauth_api_base_url}/sns/oauth2/access_token",
                params={
                    "appid": settings.wx_app_id,
                    "secret": settings.wx_app_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                },
            )
            response.raise_for_status()
            payload = response.json()
        openid = payload.get("openid")
        if not isinstance(openid, str) or not openid.strip():
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="WeChat OAuth response did not include openid",
            )
        return openid.strip()

    @classmethod
    async def authorize_callback(
        cls,
        *,
        session: AsyncSession,
        request: Request,
        code: str,
        state_token: str,
    ) -> WxDiagnosisCallbackResult:
        state = cls.decode_signed_state(state_token)
        openid = await cls.exchange_code_for_openid(code)
        delivery, employee = await cls._load_delivery_and_employee(
            session=session,
            delivery_id=state.delivery_id,
        )
        cls._validate_delivery_access(
            delivery=delivery,
            employee=employee,
            report_id=state.report_id,
            expected_fault_type=state.fault_type,
            openid=openid,
        )
        claims = WxDiagnosisCookieClaims(
            delivery_id=delivery.id,
            report_id=state.report_id,
            employee_id=employee.id,
            wx_user_id=openid,
            fault_type=state.fault_type,
            iat=_now_ts(),
            exp=_now_ts() + settings.wx_diagnosis_cookie_ttl_seconds,
        )
        portal_base = (settings.portal_base_url or settings.portal_login_url).rstrip("/")
        return WxDiagnosisCallbackResult(
            redirect_url=f"{portal_base}/wx/diagnosis/{state.report_id}",
            cookie_value=cls.create_cookie(claims),
            cookie_max_age=settings.wx_diagnosis_cookie_ttl_seconds,
            cookie_path=cls.cookie_path(),
        )

    @classmethod
    async def get_claims_from_request(
        cls,
        request: Request,
    ) -> WxDiagnosisCookieClaims:
        token = request.cookies.get(settings.wx_diagnosis_cookie_name)
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing WeChat diagnosis authorization cookie",
            )
        try:
            return cls.decode_cookie(token)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired WeChat diagnosis authorization cookie",
            ) from exc

    @classmethod
    async def authorize_report_access(
        cls,
        *,
        session: AsyncSession,
        report_id: UUID,
        claims: WxDiagnosisCookieClaims,
    ) -> DiagnosisNotificationDelivery:
        if claims.report_id != report_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="WeChat diagnosis authorization is report-scoped",
            )
        delivery, employee = await cls._load_delivery_and_employee(
            session=session,
            delivery_id=claims.delivery_id,
        )
        cls._validate_delivery_access(
            delivery=delivery,
            employee=employee,
            report_id=report_id,
            expected_fault_type=claims.fault_type,
            openid=claims.wx_user_id,
        )
        if employee.id != claims.employee_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="WeChat diagnosis authorization employee mismatch",
            )
        return delivery

    @staticmethod
    async def _load_delivery_and_employee(
        *,
        session: AsyncSession,
        delivery_id: UUID,
    ) -> tuple[DiagnosisNotificationDelivery, Employee]:
        delivery = await session.get(DiagnosisNotificationDelivery, delivery_id)
        if delivery is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="WeChat diagnosis delivery record not found",
            )
        employee = await session.get(Employee, delivery.employee_id)
        if employee is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="WeChat diagnosis recipient employee not found",
            )
        return delivery, employee

    @staticmethod
    def _validate_delivery_access(
        *,
        delivery: DiagnosisNotificationDelivery,
        employee: Employee,
        report_id: UUID,
        expected_fault_type: str | None,
        openid: str,
    ) -> None:
        if delivery.report_id != report_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="WeChat diagnosis delivery does not match report",
            )
        if expected_fault_type and delivery.fault_type != expected_fault_type:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="WeChat diagnosis delivery does not match fault scope",
            )
        if int(delivery.status) != int(DiagnosisNotificationDeliveryStatus.SENT):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="WeChat diagnosis delivery is not viewable",
            )
        snapshot_openid = _delivery_snapshot_openid(delivery)
        if snapshot_openid is None or snapshot_openid != openid:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="WeChat diagnosis recipient mismatch",
            )
        if not bool(employee.active):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="WeChat diagnosis recipient is inactive",
            )
        current_openid = (employee.wx_user_id or "").strip() or None
        if current_openid != snapshot_openid:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="WeChat diagnosis binding has changed",
            )

    @staticmethod
    def cookie_path() -> str:
        return f"{settings.api_prefix}/wx/diagnosis"


def _delivery_snapshot_openid(delivery: DiagnosisNotificationDelivery) -> str | None:
    for value in (
        getattr(delivery, "recipient_wx_user_id", None),
        getattr(delivery, "wx_user_id", None),
    ):
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _now_ts() -> int:
    return int(time.time())


def _sign_payload(payload: dict[str, Any]) -> str:
    encoded_payload = _b64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signature = _payload_signature(encoded_payload)
    return f"{encoded_payload}.{signature}"


def _verify_payload(token: str) -> dict[str, Any]:
    try:
        payload_part, signature_part = token.split(".", 1)
    except ValueError as exc:
        raise ValueError("invalid signed payload format") from exc
    expected_signature = _payload_signature(payload_part)
    if not secrets.compare_digest(expected_signature, signature_part):
        raise ValueError("invalid signed payload signature")
    try:
        payload = json.loads(_b64url_decode(payload_part).decode("utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        raise ValueError("invalid signed payload body") from exc
    exp = payload.get("exp")
    if not isinstance(exp, int) or exp <= _now_ts():
        raise ValueError("signed payload expired")
    return payload


def _payload_signature(payload_part: str) -> str:
    digest = hmac.new(
        settings.jwt_secret_key.encode("utf-8"),
        payload_part.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return _b64url_encode(digest)


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(raw + padding)
