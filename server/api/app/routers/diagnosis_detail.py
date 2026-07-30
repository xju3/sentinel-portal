"""Diagnosis detail endpoints for portal JWT and WeChat delivery-scoped access."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.wx_diagnosis_access_service import (
    WxDiagnosisAccessService,
    WxDiagnosisCookieClaims,
)
from app.utils.auth import get_current_account
from app.utils.response import success
from pub.models.customer import Account as AccountModel
from pub.services import get_session
from pub.services.diagnosis.diagnosis_report_detail_service import (
    DiagnosisReportDetailService,
)

router = APIRouter(tags=["diagnosis"])


async def get_wx_diagnosis_claims(
    request: Request,
) -> WxDiagnosisCookieClaims:
    return await WxDiagnosisAccessService.get_claims_from_request(request)


@router.get("/diagnosis/reports/{report_id}/detail")
async def get_diagnosis_report_detail(
    report_id: UUID,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    try:
        data = await DiagnosisReportDetailService.get_portal_detail(
            session=session,
            report_id=report_id,
            tenant_id=cast(UUID, current_account.tenant_id),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Diagnosis report not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Diagnosis report is outside current tenant") from exc
    return success(data)


@router.get("/wx/diagnosis/reports/{report_id}")
async def get_wx_diagnosis_report_detail(
    report_id: UUID,
    claims: WxDiagnosisCookieClaims = Depends(get_wx_diagnosis_claims),
    session: AsyncSession = Depends(get_session),
):
    await WxDiagnosisAccessService.authorize_report_access(
        session=session,
        report_id=report_id,
        claims=claims,
    )
    try:
        data = await DiagnosisReportDetailService.get_report_detail(
            session=session,
            report_id=report_id,
            fault_type=claims.fault_type,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Diagnosis report not found") from exc
    return success(data)
