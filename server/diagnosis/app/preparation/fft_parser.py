import struct
import logging
from dataclasses import dataclass

from pub.manager.database import minio_manager

logger = logging.getLogger(__name__)

@dataclass
class FftData:
    sn: str
    ts: int
    points: int
    fs: float
    range_g: int
    x_axis: list[float]
    y_axis: list[float]
    z_axis: list[float]

class FftParser:
    """
    Parses the 32-byte header + binary float array FFT data from MinIO.
    """
    @staticmethod
    def parse_from_minio(task_id: str) -> FftData | None:
        client = minio_manager.get_client()
        try:
            response = client.get_object("fft", str(task_id))
            data = response.read()
            response.close()
            response.release_conn()
        except Exception as e:
            logger.error(f"Failed to download FFT data for task {task_id} from MinIO: {e}")
            return None

        if len(data) < 32:
            logger.error(f"FFT data for task {task_id} is too short ({len(data)} bytes).")
            return None

        try:
            # 16 bytes string (SN)
            sn = data[:16].decode('ascii', errors='ignore').strip('\x00')
            # uint32 ts
            ts = struct.unpack('<I', data[16:20])[0]
            # uint32 points
            points = struct.unpack('<I', data[20:24])[0]
            # float fs
            fs = struct.unpack('<f', data[24:28])[0]
            # uint32 range
            range_g = struct.unpack('<I', data[28:32])[0]
            
            # The rest are floats for X, Y, Z axes
            remaining_bytes = len(data) - 32
            expected_floats = points * 3
            
            if remaining_bytes < expected_floats * 4:
                logger.error(f"FFT data truncated. Expected {expected_floats*4} bytes, got {remaining_bytes}")
                return None
                
            floats = struct.unpack(f'<{expected_floats}f', data[32:32 + expected_floats * 4])
            
            x_axis = list(floats[0:points])
            y_axis = list(floats[points:2*points])
            z_axis = list(floats[2*points:3*points])
            
            return FftData(
                sn=sn,
                ts=ts,
                points=points,
                fs=fs,
                range_g=range_g,
                x_axis=x_axis,
                y_axis=y_axis,
                z_axis=z_axis
            )
        except Exception as e:
            logger.error(f"Failed to parse FFT binary for task {task_id}: {e}", exc_info=True)
            return None
