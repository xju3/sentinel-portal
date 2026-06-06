"""
Admin management endpoints - for admin backend only, no tenant filtering
"""

import logging
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from uuid import UUID

logger = logging.getLogger(__name__)

from app.utils.response import success
from pub.services.dependencies import get_session
from pub.services.sensor_service import SensorBatchService
from pub.models.customer import Account
from app.utils.auth import get_current_account
from app.contract.admin import SensorBatchResponse
from app.contract.admin_firmware import (
    SensorFirmwareCreate,
    SensorFirmwareUpdate,
    SensorFirmwareResponse,
    PresignedUploadRequest,
    PresignedUploadResponse,
)
from pub.services.firmware_service import SensorFirmwareService
from app.database import minio_manager
from app.config import settings

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/sensor-batches")
async def list_all_sensor_batches(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
):
    """List all sensor batches across all tenants (admin only)"""
    return success(await SensorBatchService.get_all(session, skip, limit))


@router.get("/sensor-batches/{obj_id}")
async def get_sensor_batch(
    obj_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
):
    """Get a sensor batch by id (admin only, no tenant check)"""
    obj = await SensorBatchService.get_by_id(session, obj_id)
    if not obj:
        raise HTTPException(status_code=404, detail="SensorBatch not found")
    return success(obj)


# ==========================================
# Sensor Firmware Management
# ==========================================


@router.get("/sensor-firmwares")
async def list_sensor_firmwares(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
):
    items = await SensorFirmwareService.get_all(session, skip, limit)
    return success([SensorFirmwareResponse.model_validate(item) for item in items])


@router.post("/sensor-firmwares")
async def create_sensor_firmware(
    item: SensorFirmwareCreate,
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
):
    return success(await SensorFirmwareService.create(session, item.model_dump()))


@router.put("/sensor-firmwares/{obj_id}")
async def update_sensor_firmware(
    obj_id: UUID,
    item: SensorFirmwareUpdate,
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
):
    db_obj = await SensorFirmwareService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="SensorFirmware not found")
    if db_obj.status == 1:
        raise HTTPException(status_code=400, detail="Cannot modify a released firmware")
    return success(await SensorFirmwareService.update(session, db_obj, item.model_dump(exclude_unset=True)))


@router.delete("/sensor-firmwares/{obj_id}")
async def delete_sensor_firmware(
    obj_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
):
    db_obj = await SensorFirmwareService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="SensorFirmware not found")
    await SensorFirmwareService.delete(session, db_obj)
    return success({"message": "SensorFirmware deleted successfully"})


@router.post("/sensor-firmwares/{obj_id}/release")
async def release_sensor_firmware(
    obj_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
):
    try:
        firmware = await SensorFirmwareService.release_firmware(session, obj_id)
        return success(SensorFirmwareResponse.model_validate(firmware))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sensor-firmwares/presigned-upload")
async def get_presigned_upload_url(
    req: PresignedUploadRequest,
    current_account: Account = Depends(get_current_account),
):
    """Get a presigned upload URL for firmware file upload to MinIO.

    The file will be stored in the 'oat' bucket under the path:
    {version}/{filename}
    """
    client = minio_manager.get_client()
    bucket_name = "ota"

    # Build the object name: version/filename
    object_name = f"{req.version}/{req.filename}"

    try:
        # Ensure the bucket exists before generating the presigned URL
        if not client.bucket_exists(bucket_name):
            client.make_bucket(bucket_name)
            logger.info(f"Created MinIO bucket: {bucket_name}")

        presigned_url = client.presigned_put_object(
            bucket_name,
            object_name,
            expires=timedelta(hours=1),
        )

        # Construct the file URL (public access URL)
        endpoint = settings.minio_endpoint
        file_url = f"http://{endpoint}/{bucket_name}/{object_name}"

        return success(PresignedUploadResponse(
            presigned_url=presigned_url,
            file_url=file_url,
            object_name=object_name,
        ))
    except Exception as e:
        logger.error(f"Failed to generate presigned URL: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate upload URL: {str(e)}")
