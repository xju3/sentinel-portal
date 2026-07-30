import logging
import struct
from dataclasses import dataclass

from pub.manager.database import minio_manager

logger = logging.getLogger(__name__)

@dataclass
class FftData:
    sn_hint: str
    timestamp_s: int
    points: int
    spectrum_bins: int
    fs: float
    range_g: int
    x_axis: list[float]
    y_axis: list[float]
    z_axis: list[float]


def build_preview_payload(
    fft_data: FftData,
) -> dict[str, object]:
    preview_length = min(
        fft_data.spectrum_bins,
        len(fft_data.x_axis),
        len(fft_data.y_axis),
        len(fft_data.z_axis),
    )
    indices = list(range(preview_length))
    freq_res = fft_data.fs / fft_data.points if fft_data.points > 0 else 0.0

    return {
        "ts_ms": fft_data.timestamp_s * 1000,
        "fs_hz": fft_data.fs,
        "range_g": fft_data.range_g,
        "fft_size": fft_data.points,
        "spectrum_bins": fft_data.spectrum_bins,
        "points_preview": preview_length,
        "freq_hz": [round(index * freq_res, 6) for index in indices],
        "x_axis": _copy_axis(fft_data.x_axis, indices),
        "y_axis": _copy_axis(fft_data.y_axis, indices),
        "z_axis": _copy_axis(fft_data.z_axis, indices),
    }


def _copy_axis(axis: list[float], indices: list[int]) -> list[float]:
    return [round(float(axis[index]), 6) for index in indices]

class FftParser:
    """
    Parses the 32-byte header + binary float array FFT data from MinIO.
    """
    @staticmethod
    def parse_from_minio(task_id: str) -> FftData | None:
        client = minio_manager.get_client()
        try:
            response = client.get_object(minio_manager.bucket_name, str(task_id))
            data = response.read()
            response.close()
            response.release_conn()
        except Exception as e:
            logger.error(f"Failed to download FFT data for task {task_id} from MinIO: {e}")
            return None

        return FftParser.parse_bytes(data, source=str(task_id))

    @staticmethod
    def parse_bytes(data: bytes, *, source: str = "<bytes>") -> FftData | None:
        if len(data) < 32:
            logger.error("FFT data for %s is too short (%s bytes).", source, len(data))
            return None
        try:
            # 16 bytes string (SN)
            sn_hint = data[:16].decode('ascii', errors='ignore').strip('\x00')
            # uint32 Unix timestamp in seconds. A millisecond epoch cannot fit
            # in this field; normalize it only after parsing.
            timestamp_s = struct.unpack('<I', data[16:20])[0]
            # uint32 points
            points = struct.unpack('<I', data[20:24])[0]
            # float fs
            fs = struct.unpack('<f', data[24:28])[0]
            # uint32 range
            range_g = struct.unpack('<I', data[28:32])[0]
            
            if points <= 0 or points % 2:
                logger.error(
                    "FFT data for %s has invalid FFT size %s; expected a positive even value.",
                    source,
                    points,
                )
                return None

            # A real-valued N-point FFT uploads N/2 positive-frequency bins per axis.
            spectrum_bins = points // 2
            remaining_bytes = len(data) - 32
            expected_floats = spectrum_bins * 3
            
            if remaining_bytes != expected_floats * 4:
                logger.error(
                    "FFT data size mismatch for %s. Expected %s bytes for "
                    "3 x %s bins, got %s",
                    source,
                    expected_floats * 4,
                    spectrum_bins,
                    remaining_bytes,
                )
                return None
                
            floats = struct.unpack(f'<{expected_floats}f', data[32:32 + expected_floats * 4])
            
            x_axis = list(floats[0:spectrum_bins])
            y_axis = list(floats[spectrum_bins:2*spectrum_bins])
            z_axis = list(floats[2*spectrum_bins:3*spectrum_bins])
            
            return FftData(
                sn_hint=sn_hint,
                timestamp_s=timestamp_s,
                points=points,
                spectrum_bins=spectrum_bins,
                fs=fs,
                range_g=range_g,
                x_axis=x_axis,
                y_axis=y_axis,
                z_axis=z_axis
            )
        except Exception as e:
            logger.error("Failed to parse FFT binary for %s: %s", source, e, exc_info=True)
            return None
