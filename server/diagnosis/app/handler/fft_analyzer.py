import logging
from io import BytesIO
import json
import uuid
from typing import Any

from sqlalchemy import select

from app.preparation.fft_parser import FftData, build_preview_payload
from app.services.context import DeviceContextService
from pub.manager.database import db_manager, minio_manager
from pub.models.diagnosis import DiagnosisFft
from pub.models.sensor import DeviceFftRecord, Sensor, SensorMonitoring, SensorTask

logger = logging.getLogger(__name__)

class FftAnalyzer:
    """
    Physical diagnosis engine that processes raw FFT frequency bins 
    and applies Rotodynamics heuristics to determine root causes (Unbalance, Misalignment, Bearing, etc.).
    """
    
    @staticmethod
    async def analyze_and_save(fft_task_id: str, fft_data: FftData) -> bool:
        try:
            fft_task_uuid = uuid.UUID(fft_task_id)
            points = fft_data.points
            fs = fft_data.fs

            if points <= 0 or fs <= 0:
                logger.error(
                    "FFT Analysis aborted: invalid FFT metadata for task %s (points=%s, fs=%s)",
                    fft_task_id,
                    points,
                    fs,
                )
                return False

            # Frequency resolution
            freq_res = fs / points

            max_amp = 0.0
            max_freq = 0.0
            max_axis = "X"

            # Find the dominant frequency peak across all 3 axes
            for axis_name, axis_data in [
                ("X", fft_data.x_axis),
                ("Y", fft_data.y_axis),
                ("Z", fft_data.z_axis),
            ]:
                for i, amp in enumerate(axis_data):
                    # Ignore DC component (0 Hz)
                    if i == 0:
                        continue

                    if amp > max_amp:
                        max_amp = amp
                        max_freq = i * freq_res
                        max_axis = axis_name

            async with db_manager.SessionLocal() as session:
                task_stmt = select(SensorTask).where(SensorTask.id == fft_task_uuid)
                task = (await session.execute(task_stmt)).scalar_one_or_none()
                if task is None:
                    logger.error(
                        "FFT Analysis aborted: SensorTask %s not found",
                        fft_task_id,
                    )
                    return False

                existing_fft = (
                    await session.execute(
                        select(DiagnosisFft).where(
                            DiagnosisFft.fft_task_id == fft_task_uuid
                        )
                    )
                ).scalar_one_or_none()
                if existing_fft is not None:
                    return True

                stmt = (
                    select(SensorMonitoring.device_inst_id)
                    .join(Sensor, Sensor.id == SensorMonitoring.sensor_id)
                    .where(Sensor.sn == task.sn, SensorMonitoring.status == 1)
                )
                device_inst_id_val = (await session.execute(stmt)).scalar_one_or_none()

                if not device_inst_id_val:
                    logger.error(
                        "FFT Analysis aborted: No active sensor monitoring found for SN %s",
                        task.sn,
                    )
                    return False

                context = await DeviceContextService.get_by_device_id(session, str(device_inst_id_val))
                if not context:
                    logger.error(
                        "FFT Analysis aborted: Device context not found for device %s",
                        device_inst_id_val,
                    )
                    return False

                rpm = context.get("device_spec", {}).get("rpm", 0)
                rpm = float(rpm or 0)
                rpm_source = "device_spec" if rpm > 0 else None

                if not rpm or rpm <= 0:
                    logger.error(
                        "FFT Analysis aborted: Device RPM not configured (RPM=%s) for device %s",
                        rpm,
                        device_inst_id_val,
                    )
                    return False

                base_freq = rpm / 60.0

                # Basic Rotodynamics heuristics based on dominant frequency relative to base_freq (1X)
                fault_type = "Unknown Anomaly"
                confidence = 0.5

                # 1X = base_freq, 2X = base_freq * 2
                if base_freq * 0.9 <= max_freq <= base_freq * 1.1:
                    fault_type = "Mass Unbalance / Looseness (1X)"
                    confidence = 0.85
                elif base_freq * 1.9 <= max_freq <= base_freq * 2.1:
                    fault_type = "Misalignment (2X)"
                    confidence = 0.80
                elif max_freq > base_freq * 3.0:
                    fault_type = "Bearing Defect (High Frequency)"
                    confidence = 0.70
                else:
                    fault_type = "Structural Looseness / Low Freq Noise"
                    confidence = 0.60

                spectrum_preview_object_key = FftAnalyzer._upload_spectrum_preview(
                    fft_task_id=fft_task_id,
                    fft_data=fft_data,
                )
                device_fft_record = (
                    await session.execute(
                        select(DeviceFftRecord).where(DeviceFftRecord.task_id == fft_task_uuid)
                    )
                ).scalar_one_or_none()
                if device_fft_record is None:
                    logger.error(
                        "FFT Analysis aborted: DeviceFftRecord missing for task %s",
                        fft_task_id,
                    )
                    return False
                details = {
                    "max_amplitude_g": round(max_amp, 4),
                    "peak_frequency_hz": round(max_freq, 2),
                    "base_frequency_hz": round(base_freq, 2),
                    "dominant_axis": max_axis,
                    "analysis_mode": "Relative Peak Frequency (1X/2X) Heuristics",
                    "resolution_hz": round(freq_res, 2),
                    "spectrum_preview_points": fft_data.spectrum_bins,
                }

                fft_record = DiagnosisFft(
                    fft_task_id=fft_task_uuid,
                    device_fft_record_id=device_fft_record.id,
                    conclusion=fault_type,
                    confidence=confidence,
                    rpm_snapshot=rpm,
                    base_frequency_hz=base_freq,
                    rpm_source=rpm_source,
                    spectrum_preview_object_key=spectrum_preview_object_key,
                    details=details,
                )
                session.add(fft_record)
                await session.commit()

            logger.info(
                "FFT Analysis completed for task %s: %s (%.1f%%) at %.1fHz",
                fft_task_id,
                fault_type,
                confidence * 100,
                max_freq,
            )
            return True
        except Exception as e:
            logger.error(
                "Failed to analyze FFT data for task %s: %s",
                fft_task_id,
                e,
                exc_info=True,
            )
            return False

    @staticmethod
    def _upload_spectrum_preview(fft_task_id: str, fft_data: FftData) -> str | None:
        preview_payload = build_preview_payload(fft_data)
        if not preview_payload["points_preview"]:
            return None
        preview_object_key = f"preview/{fft_task_id}.json"
        preview_bytes = json.dumps(preview_payload, ensure_ascii=False).encode("utf-8")
        client = minio_manager.get_client()
        client.put_object(
            bucket_name=minio_manager.bucket_name,
            object_name=preview_object_key,
            data=BytesIO(preview_bytes),
            length=len(preview_bytes),
            content_type="application/json",
        )
        return preview_object_key
