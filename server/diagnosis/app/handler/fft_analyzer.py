import logging
import uuid
from typing import Any

from sqlalchemy import select

from pub.manager.database import db_manager
from pub.models.diagnosis import DiagnosisFft
from app.preparation.fft_parser import FftData

logger = logging.getLogger(__name__)

class FftAnalyzer:
    """
    Physical diagnosis engine that processes raw FFT frequency bins 
    and applies Rotodynamics heuristics to determine root causes (Unbalance, Misalignment, Bearing, etc.).
    """
    
    @staticmethod
    async def analyze_and_save(fft_task_id: str, fft_data: FftData) -> None:
        try:
            points = fft_data.points
            fs = fft_data.fs
            
            # Frequency resolution
            freq_res = (fs / 2.0) / points
            
            max_amp = 0.0
            max_freq = 0.0
            max_axis = "X"
            
            # Find the dominant frequency peak across all 3 axes
            for axis_name, axis_data in [("X", fft_data.x_axis), ("Y", fft_data.y_axis), ("Z", fft_data.z_axis)]:
                for i, amp in enumerate(axis_data):
                    # Ignore DC component (0 Hz)
                    if i == 0:
                        continue
                        
                    if amp > max_amp:
                        max_amp = amp
                        max_freq = i * freq_res
                        max_axis = axis_name
            
            async with db_manager.SessionLocal() as session:
                # 1. Fetch Device Instance ID by SN
                from pub.models.sensor import Sensor, SensorMonitoring
                stmt = select(SensorMonitoring.device_inst_id).join(Sensor, Sensor.id == SensorMonitoring.sensor_id).where(Sensor.sn == fft_data.sn, SensorMonitoring.status == 1)
                device_inst_id_val = (await session.execute(stmt)).scalar_one_or_none()
                
                if not device_inst_id_val:
                    logger.error(f"FFT Analysis aborted: No active sensor monitoring found for SN {fft_data.sn}")
                    return
                    
                # 2. Fetch Device Context to get actual RPM
                from app.services.context import DeviceContextService
                context = await DeviceContextService.get_by_device_id(session, str(device_inst_id_val))
                if not context:
                    logger.error(f"FFT Analysis aborted: Device context not found for device {device_inst_id_val}")
                    return
                    
                rpm = context.get("spec", {}).get("rpm", 0)
                if not rpm or rpm <= 0:
                    logger.error(f"FFT Analysis aborted: Device RPM not configured (RPM={rpm}) for device {device_inst_id_val}")
                    return
                    
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
                    
                details = {
                    "max_amplitude_g": round(max_amp, 4),
                    "peak_frequency_hz": round(max_freq, 2),
                    "base_frequency_hz": round(base_freq, 2),
                    "dominant_axis": max_axis,
                    "analysis_mode": "Relative Peak Frequency (1X/2X) Heuristics",
                    "resolution_hz": round(freq_res, 2)
                }
            
                async with session.begin():
                    # We use the fft_task_id as a fallback report_id if we don't have the original report
                    # that triggered it. In a robust system, we would trace back the task generation chain.
                    fft_record = DiagnosisFft(
                        report_id=str(fft_task_id),
                        fft_task_id=uuid.UUID(fft_task_id),
                        conclusion=fault_type,
                        confidence=confidence,
                        details=details
                    )
                    session.add(fft_record)
                    
            logger.info(f"FFT Analysis completed for task {fft_task_id}: {fault_type} ({confidence*100:.1f}%) at {max_freq:.1f}Hz")
            
        except Exception as e:
            logger.error(f"Failed to analyze FFT data for task {fft_task_id}: {e}", exc_info=True)
