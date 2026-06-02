from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from pub.services.dependencies import get_session
from pub.services.sensor_service import SensorService
from app.contract.common import ApiResponse

router = APIRouter(tags=["Sensor Trends"])

@router.get("/sensors/{sn}/history")
async def get_sensor_history(
    sn: str,
    range: str = Query("1w", description="Time range: 1w, 2w, 1m, 2m, 3m"),
    window: Optional[str] = Query(None, description="Aggregation window: auto, 1h, 4h, 8h, 12h, 1d"),
    session: AsyncSession = Depends(get_session)
):
    data = await SensorService.get_sensor_history(session, sn, range, window)
    return ApiResponse(code=0, message="success", data=data)