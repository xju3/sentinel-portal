import json
from typing import Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

class TimeFeature(BaseModel):
    mean_g: float | None = None
    rms_acc_g: float | None = None
    peak_acc_g: float | None = None
    peak_to_peak_acc_g: float | None = None
    rms_vel_mm_s: float | None = None
    peak_to_peak_disp_um: float | None = None
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


class BearingFaultCandidate(BaseModel):
    """One measured envelope-spectrum candidate sent by the device."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    harmonic: int = Field(ge=1, le=16)
    observed_hz: float = Field(gt=0)
    snr_db: float


class BearingFaultCandidates(BaseModel):
    """Candidates are grouped by fault family; empty groups may be omitted."""

    model_config = ConfigDict(extra="forbid")

    bpfo: List[BearingFaultCandidate] = Field(default_factory=list, max_length=16)
    bpfi: List[BearingFaultCandidate] = Field(default_factory=list, max_length=16)
    bsf: List[BearingFaultCandidate] = Field(default_factory=list, max_length=16)
    ftf: List[BearingFaultCandidate] = Field(default_factory=list, max_length=16)


class BearingAxisFeatures(BaseModel):
    """Dynamic bearing evidence for one physical accelerometer axis."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    status: Literal[0, 1] = Field(
        description="0=analysis complete, 1=insufficient data"
    )
    envelope_kurtosis: float | None = Field(default=None, ge=0)
    fault_candidates: BearingFaultCandidates = Field(default_factory=BearingFaultCandidates)

    @field_validator("status", mode="before")
    @classmethod
    def _reject_boolean_status(cls, value):
        if isinstance(value, bool):
            raise ValueError("status must be 0 or 1, not boolean")
        return value


class BearingFeatures(BaseModel):
    """Per-cycle edge-computed evidence; stable bearing configuration is server-owned."""

    model_config = ConfigDict(extra="forbid")

    X: BearingAxisFeatures
    Y: BearingAxisFeatures
    Z: BearingAxisFeatures

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
    bearing_features: BearingFeatures | None = None

class DiagnosisTriggerPayload(BaseModel):
    report_id: str
    schema_version: str | None = "1.0"
    sensor_sn: str
    device_id: str
    temperature_c: float | None = None
    max_rms_vel: float
    max_p2p_disp: float | None = None
    fs_hz: int | None = None
    points: int | None = None
    task_id: str | None = None
    delay: int | None = 0
    total: int
    sensor_id: str | None = None
    location_id: str
    tenant_id: str | None = None
    region_id: str | None = None
    device_category_id: str | None = None
    process_device_id: str | None = None
    ts_ms: int
    bearing_features: BearingFeatures | None = None

    @field_validator("bearing_features", mode="before")
    @classmethod
    def _parse_bearing_features(cls, value):
        if isinstance(value, (str, bytes, bytearray)):
            return json.loads(value)
        return value
