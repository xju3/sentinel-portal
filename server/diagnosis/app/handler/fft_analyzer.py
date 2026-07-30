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
    Generic FFT screening engine that processes uploaded magnitude spectra and
    applies bounded 1X/2X peak heuristics without claiming bearing-envelope diagnosis.
    """

    _ANALYSIS_MODE = "Configured-RPM Magnitude Spectrum Screening"
    _GENERIC_ANALYSIS_MODE = "Generic Magnitude Spectrum Screening"
    _BASE_LIMITATIONS = [
        "Uses uploaded magnitude bins only; phase and time waveform are unavailable.",
        "No envelope/demodulation analysis is performed, so bearing defect frequencies cannot be confirmed.",
    ]
    
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

                rpm = (context.get("device_spec") or {}).get("rpm", 0)
                rpm = float(rpm or 0)
                rpm_source = "device_spec" if rpm > 0 else None
                base_freq = rpm / 60.0 if rpm > 0 else None
                analysis_mode = (
                    FftAnalyzer._ANALYSIS_MODE
                    if base_freq is not None
                    else FftAnalyzer._GENERIC_ANALYSIS_MODE
                )
                bearing_references = FftAnalyzer._bearing_references(context)
                has_bearing_configuration = bool(context.get("bearing_bindings"))
                has_bearing_frequency_inputs = bool(bearing_references)
                analysis_limitations = FftAnalyzer._build_analysis_limitations(
                    has_rpm=base_freq is not None,
                    has_bearing_configuration=has_bearing_configuration,
                    has_bearing_frequency_inputs=has_bearing_frequency_inputs,
                )

                # Basic spectrum screening based on dominant frequency relative to base_freq (1X).
                fault_type = "Dominant Spectrum Peak"
                confidence = 0.5
                dominant_ratio = (
                    max_freq / base_freq if base_freq is not None else None
                )

                # 1X = base_freq, 2X = base_freq * 2
                if base_freq is None:
                    fault_type = "Generic Spectrum Observation"
                    confidence = 0.4
                elif base_freq * 0.9 <= max_freq <= base_freq * 1.1:
                    fault_type = "Mass Unbalance / Looseness (1X)"
                    confidence = 0.85
                elif base_freq * 1.9 <= max_freq <= base_freq * 2.1:
                    fault_type = "Misalignment (2X)"
                    confidence = 0.80
                elif max_freq > base_freq * 3.0:
                    fault_type = "High Frequency Excitation (>3X)"
                    confidence = 0.70
                else:
                    fault_type = "Structural Looseness / Low Freq Noise"
                    confidence = 0.60

                spectrum_preview_object_key = FftAnalyzer._upload_spectrum_preview(
                    fft_task_id=fft_task_id,
                    fft_data=fft_data,
                    analysis_metadata=FftAnalyzer._build_plot_metadata(
                        analysis_limitations=analysis_limitations,
                        max_amp=max_amp,
                        max_axis=max_axis,
                        max_freq=max_freq,
                        base_freq=base_freq,
                        dominant_ratio=dominant_ratio,
                        analysis_mode=analysis_mode,
                        bearing_references=bearing_references,
                        resolution_hz=freq_res,
                    ),
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
                    "base_frequency_hz": (
                        round(base_freq, 2) if base_freq is not None else None
                    ),
                    "dominant_ratio_to_1x": (
                        round(dominant_ratio, 3)
                        if dominant_ratio is not None
                        else None
                    ),
                    "dominant_axis": max_axis,
                    "analysis_mode": analysis_mode,
                    "resolution_hz": round(freq_res, 2),
                    "spectrum_preview_points": fft_data.spectrum_bins,
                    "analysis_limitations": analysis_limitations,
                    "bearing_frequency_inputs_available": has_bearing_frequency_inputs,
                    "bearing_bindings_configured": has_bearing_configuration,
                    "plot_metadata": FftAnalyzer._build_plot_metadata(
                        analysis_limitations=analysis_limitations,
                        max_amp=max_amp,
                        max_axis=max_axis,
                        max_freq=max_freq,
                        base_freq=base_freq,
                        dominant_ratio=dominant_ratio,
                        analysis_mode=analysis_mode,
                        bearing_references=bearing_references,
                        resolution_hz=freq_res,
                    ),
                }

                fft_record = DiagnosisFft(
                    fft_task_id=fft_task_uuid,
                    device_fft_record_id=device_fft_record.id,
                    conclusion=fault_type,
                    confidence=confidence,
                    rpm_snapshot=rpm if rpm > 0 else None,
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
    def _upload_spectrum_preview(
        fft_task_id: str,
        fft_data: FftData,
        analysis_metadata: dict[str, Any] | None = None,
    ) -> str | None:
        preview_payload = build_preview_payload(fft_data)
        if not preview_payload["points_preview"]:
            return None
        if analysis_metadata:
            preview_payload["analysis"] = analysis_metadata
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

    @staticmethod
    def _build_plot_metadata(
        *,
        analysis_limitations: list[str],
        max_amp: float,
        max_axis: str,
        max_freq: float,
        base_freq: float | None,
        dominant_ratio: float | None,
        analysis_mode: str,
        bearing_references: list[dict[str, Any]],
        resolution_hz: float,
    ) -> dict[str, Any]:
        reference_markers = {}
        if base_freq is not None:
            reference_markers = {
                "1x": round(base_freq, 2),
                "2x": round(base_freq * 2, 2),
                "3x": round(base_freq * 3, 2),
            }
        bearing_match_hints = FftAnalyzer._bearing_match_hints(
            max_freq=max_freq,
            resolution_hz=resolution_hz,
            bearing_references=bearing_references,
        )
        return {
            "mode": analysis_mode,
            "limitations": list(analysis_limitations),
            "dominant_peak": {
                "axis": max_axis,
                "frequency_hz": round(max_freq, 2),
                "amplitude_g": round(max_amp, 4),
                "ratio_to_1x": (
                    round(dominant_ratio, 3)
                    if dominant_ratio is not None
                    else None
                ),
            },
            "reference_markers_hz": reference_markers,
            "bearing_reference_markers": bearing_references,
            "bearing_match_hints": bearing_match_hints,
            "bearing_frequency_inputs_available": bool(bearing_references),
            "envelope_analysis_performed": False,
        }

    @staticmethod
    def _build_analysis_limitations(
        *,
        has_rpm: bool,
        has_bearing_configuration: bool,
        has_bearing_frequency_inputs: bool,
    ) -> list[str]:
        limitations = list(FftAnalyzer._BASE_LIMITATIONS)
        if has_rpm:
            limitations.append(
                "Configured RPM is used as the 1X reference; live shaft speed during acquisition is unknown."
            )
        else:
            limitations.append(
                "Device RPM is not configured; 1X/2X/3X and bearing-frequency reference markers are unavailable."
            )
        if not has_bearing_configuration:
            limitations.append(
                "Missing bearing geometry/fault-frequency parameters prevent BPFI/BPFO/BSF matching."
            )
        elif has_rpm and not has_bearing_frequency_inputs:
            limitations.append(
                "Configured bearing parameters are incomplete or invalid; BPFI/BPFO/BSF/FTF markers are unavailable."
            )
        return limitations

    @staticmethod
    def _bearing_references(context: dict[str, Any]) -> list[dict[str, Any]]:
        references = []
        for binding in context.get("bearing_bindings") or []:
            if not isinstance(binding, dict):
                continue
            frequencies = binding.get("frequency_reference_hz")
            if not isinstance(frequencies, dict):
                continue
            required = ("BPFO", "BPFI", "BSF", "FTF")
            try:
                normalized = {
                    key: round(float(frequencies[key]), 3)
                    for key in required
                    if float(frequencies[key]) > 0
                }
            except (KeyError, TypeError, ValueError):
                continue
            if len(normalized) != len(required):
                continue
            bearing = binding.get("bearing") or {}
            references.append(
                {
                    "binding_id": binding.get("id"),
                    "location_id": binding.get("location_id"),
                    "bearing": {
                        "id": bearing.get("id"),
                        "brand": bearing.get("brand"),
                        "model": bearing.get("model"),
                    },
                    "frequencies_hz": normalized,
                    "bsf_definition": (
                        "Rolling-element spin frequency; this marker is BSF, not 2x BSF."
                    ),
                }
            )
        return references

    @staticmethod
    def _bearing_match_hints(
        *,
        max_freq: float,
        resolution_hz: float,
        bearing_references: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        hints = []
        for reference in bearing_references:
            for frequency_name, frequency_hz in reference["frequencies_hz"].items():
                tolerance_hz = max(resolution_hz * 1.5, frequency_hz * 0.03)
                delta_hz = abs(max_freq - frequency_hz)
                if delta_hz <= tolerance_hz:
                    hints.append(
                        {
                            "binding_id": reference["binding_id"],
                            "location_id": reference["location_id"],
                            "frequency_name": frequency_name,
                            "reference_hz": frequency_hz,
                            "observed_hz": round(max_freq, 3),
                            "delta_hz": round(delta_hz, 3),
                            "tolerance_hz": round(tolerance_hz, 3),
                            "interpretation": (
                                "Dominant magnitude-spectrum peak is near this configured "
                                "reference; envelope analysis is required for confirmation."
                            ),
                        }
                    )
        return hints
