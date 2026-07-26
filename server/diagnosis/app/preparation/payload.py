from typing import Dict, List
from pydantic import BaseModel, Field

class TimeFeature(BaseModel):
    mean_g: float | None = None
    rms_acc_g: float | None = None
    peak_acc_g: float | None = None
    peak_to_peak_acc_g: float | None = None
    rms_vel_mm_s: float | None = None
    crest_factor: float | None = None
    kurtosis: float | None = None

class FreqPeak(BaseModel):
    freq_hz: float
    amp_g: float

class FreqFeature(BaseModel):
    peaks: List[FreqPeak] | None = None
    spectral_centroid_hz: float | None = None
    spectral_entropy: float | None = None

class AxisFeature(BaseModel):
    """
    Features for a single axis (e.g. X, Y, Z) computed at the edge.
    """
    time: TimeFeature | None = None
    freq: FreqFeature | None = None
    band_energy_ratio: Dict[str, float] | None = None

class DataQuality(BaseModel):
    status: int
    auto_range: bool


class DeviceDiagnosticReport(BaseModel):
    """
    The top-level payload structure received from the edge/hardware.
    """
    schema_version: int | None = None
    sensor_sn: str
    device_id: str
    report_id: str
    delay: int = 0
    total: int = 0
    ts_ms: int = Field(..., description="Actual data sampling/measurement timestamp in Unix milliseconds")
    
    # Global metrics
    temperature_c: float | None = None
    fs_hz: int | None = None
    requested_range_g: float | None = None
    range_g: float | None = None
    points: int | None = None
    duration_ms: float | None = Field(None, description="Active processing and 4G module startup time before upload (battery/performance metric)")
    
    # Device identity metadata (flattened from sensor_meta at ingest time)
    sensor_id: str | None = None
    location_id: str | None = None
    tenant_id: str | None = None
    region_id: str | None = None
    device_category_id: str | None = None
    process_device_id: str | None = None
    rpm: float | None = None
    
    # Payload metadata
    sample_type: str | None = None
    task_id: str | None = None
    quality: DataQuality | None = None
    
    # The actual feature data per axis
    axis_features: Dict[str, AxisFeature] = Field(default_factory=dict, description="Pre-computed features for X, Y, Z axes")
