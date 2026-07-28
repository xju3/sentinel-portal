import logging
from typing import Any
from dataclasses import dataclass

from pub.services.trend_cache import TrendCacheService
from app.services.baseline_service import BaselineService

logger = logging.getLogger(__name__)

@dataclass
class VibrationDiagnosisResult:
    status: str
    severity: str
    reason: str
    evidence: dict[str, Any]
    requires_resampling: bool = False

class VibrationDiagnosis:
    """
    Vibration diagnostic engine.
    
    动态定级基准：振动载荷占比 (Vibration Budget Ratio)
    ratio = 当前速度有效值 (max_rms_vel) / baseline
    以此占比划分区间：<10% (Info), 10~20% (Attention), 20~40% (Abnormal), 40~70% (Warning), >=70% (Critical)。
    所有的历史趋势违规（短期/中期斜率与振幅）以及横向对等组比较违规，均由该 ratio 对应的区间决定其严重程度。
    """

    @staticmethod
    def _calculate_slope(trend_data: list[dict[str, Any]]) -> float:
        if len(trend_data) < 2:
            return 0.0
            
        n = len(trend_data)
        sum_x = sum(i for i in range(n))
        sum_y = sum(pt["value"] for pt in trend_data)
        sum_xy = sum(i * pt["value"] for i, pt in enumerate(trend_data))
        sum_xx = sum(i * i for i in range(n))
        
        denominator = n * sum_xx - sum_x * sum_x
        if denominator == 0:
            return 0.0
            
        slope_per_point = (n * sum_xy - sum_x * sum_y) / denominator
        # Convert to change per hour (assuming roughly 1 point per 5 mins => 12 points/hr)
        return slope_per_point * 12.0

    @staticmethod
    def _calculate_amplitude(trend_data: list[dict[str, Any]], current_val: float) -> float:
        if not trend_data:
            return 0.0
        min_val = min(pt["value"] for pt in trend_data)
        max_val = max(pt["value"] for pt in trend_data)
        max_val = max(max_val, current_val)
        min_val = min(min_val, current_val)
        return max_val - min_val

    @staticmethod
    def _get_severity_from_ratio(ratio: float) -> str:
        if ratio < 0.10:
            return "info"
        elif ratio < 0.20:
            return "attention"
        elif ratio < 0.40:
            return "abnormal"
        elif ratio < 0.70:
            return "warning"
        else:
            return "critical"

    @staticmethod
    def _escalate(current_severity: str, new_severity: str) -> str:
        levels = {"ok": 0, "info": 0, "attention": 1, "abnormal": 2, "warning": 3, "critical": 4}
        if levels.get(new_severity, 0) > levels.get(current_severity, 0):
            return new_severity
        return current_severity

    @staticmethod
    async def analyze(
        device_id: str,
        location_id: str,
        max_rms_vel: float,
        context: dict[str, Any],
        current_ts_ms: int | None = None,
    ) -> dict[str, Any]:
        logger.info("Running vibration diagnosis for device=%s, location=%s, rms_vel=%.2f", 
                    device_id, location_id, max_rms_vel)

        # 1. Fetch threshold configuration
        thresholds = context.get("thresholds", {}).get("vibration", {})
        baseline = float(thresholds.get("baseline", 11.0))
        
        # 动态获取健康基线 (设备自学习或周期性滚动生成的中位数)
        healthy_median = await BaselineService.get_active_baseline(device_id, "max_rms_vel")
        
        rt_max_delta = float(thresholds.get("rt_max_delta", 5.0))
        st_max_amplitude = float(thresholds.get("st_max_amplitude", 3.0))
        st_max_slope = float(thresholds.get("st_max_slope", 1.0))
        mt_max_amplitude = float(thresholds.get("mt_max_amplitude", 4.0))
        mt_max_slope = float(thresholds.get("mt_max_slope", 0.5))

        evidence = {"current": max_rms_vel, "healthy_median": healthy_median}
        
        # Base Ratio calculation: (current - healthy) / (baseline - healthy)
        if baseline > healthy_median:
            ratio = (max_rms_vel - healthy_median) / (baseline - healthy_median)
        else:
            ratio = 0.0
        ratio = max(0.0, ratio) # 防止当前值低于健康中位数时出现负数
        
        evidence["vibration_budget_ratio"] = round(ratio, 4)
        context_severity = VibrationDiagnosis._get_severity_from_ratio(ratio)

        # 1. Absolute Baseline Check
        if max_rms_vel >= baseline:
            return {
                "status": "alarm",
                "severity": "critical",
                "reason": f"Critical: Absolute vibration {max_rms_vel:.2f} mm/s exceeded baseline {baseline} mm/s!",
                "evidence": evidence,
                "requires_resampling": True
            }
            
        # Warning Zone baseline check
        if ratio >= 0.70:
            return {
                "status": "alarm",
                "severity": "warning",
                "reason": f"Warning: Vibration {max_rms_vel:.2f} mm/s reached {ratio*100:.1f}% of baseline.",
                "evidence": evidence,
                "requires_resampling": True
            }

        trend_data = await TrendCacheService.get_recent_trend(location_id, "rms_vel_mm_s")
        if current_ts_ms is not None:
            trend_data = [
                point for point in trend_data
                if point["ts_ms"] <= current_ts_ms
            ]
        previous_trend = [
            point for point in trend_data
            if current_ts_ms is None or point["ts_ms"] < current_ts_ms
        ]
        
        # 2. Real-Time Mutation Check (Mutation => Requires Resampling)
        if previous_trend:
            last_val = previous_trend[-1]["value"]
            mutation = abs(max_rms_vel - last_val)
            evidence["mutation"] = mutation
            evidence["last_val"] = last_val
            if mutation > rt_max_delta:
                return {
                    "status": "alarm",
                    "severity": "warning",
                    "reason": f"Warning: Real-time mutation {mutation:.2f} mm/s exceeds limit {rt_max_delta} mm/s!",
                    "evidence": evidence,
                    "requires_resampling": True
                }

        severity = context_severity
        alarm_reason = ""
        
        # 3. Horizontal Peer Group Deviation Check (Deviation => Requires Resampling)
        peer_group = context.get("peer_group", {})
        if peer_group.get("enabled") and peer_group.get("members"):
            peer_values = []
            for member in peer_group["members"]:
                peer_loc_id = member.get("location_id")
                if peer_loc_id and peer_loc_id != location_id:
                    peer_trend = await TrendCacheService.get_recent_trend(peer_loc_id, "rms_vel_mm_s")
                    if peer_trend and len(peer_trend) > 0:
                        peer_values.append(peer_trend[-1]["value"])
            
            if peer_values:
                # Remove min/max extremes if enough data
                if len(peer_values) >= 3:
                    peer_values.remove(max(peer_values))
                    peer_values.remove(min(peer_values))
                
                peer_median = sorted(peer_values)[len(peer_values) // 2]
                evidence["peer_median"] = peer_median
                
                # Check deviation (e.g. 5.0 mm/s)
                if abs(max_rms_vel - peer_median) > 5.0:
                    severity = VibrationDiagnosis._escalate(severity, "abnormal")
                    alarm_reason = f"Peer deviation: current {max_rms_vel:.2f} mm/s differs from peer median {peer_median:.2f} mm/s."
                    
                    return {
                        "status": "alarm",
                        "severity": severity,
                        "reason": alarm_reason,
                        "evidence": evidence,
                        "requires_resampling": True
                    }

        # 4. Long/Short Term Trend Checks (Trend => NO Resampling, just alarm)
        # Use 24h for ST, 72h for MT
        # Note: Trend checks only escalate based on context_severity
        if trend_data:
            # We approximate ST as last 288 points, MT as all (up to 864 points) based on 5min intervals
            st_trend = trend_data[-288:] if len(trend_data) > 288 else trend_data
            mt_trend = trend_data
            
            st_slope = VibrationDiagnosis._calculate_slope(st_trend)
            st_amplitude = VibrationDiagnosis._calculate_amplitude(st_trend, max_rms_vel)
            evidence["st_slope"] = round(st_slope, 4)
            evidence["st_amplitude"] = round(st_amplitude, 4)
            
            if abs(st_slope) > st_max_slope or st_amplitude > st_max_amplitude:
                severity = VibrationDiagnosis._escalate(severity, context_severity)
                alarm_reason = "Violated Short-Term trend."
                
            mt_slope = VibrationDiagnosis._calculate_slope(mt_trend)
            mt_amplitude = VibrationDiagnosis._calculate_amplitude(mt_trend, max_rms_vel)
            evidence["mt_slope"] = round(mt_slope, 4)
            evidence["mt_amplitude"] = round(mt_amplitude, 4)
            
            if not alarm_reason and (abs(mt_slope) > mt_max_slope or mt_amplitude > mt_max_amplitude):
                severity = VibrationDiagnosis._escalate(severity, context_severity)
                alarm_reason = "Violated Middle-Term trend."

        if alarm_reason:
            return {
                "status": "alarm",
                "severity": severity,
                "reason": alarm_reason,
                "evidence": evidence,
                "requires_resampling": False
            }

        return {
            "status": "ok",
            "severity": severity,
            "reason": f"Running normally at {max_rms_vel:.2f} mm/s",
            "evidence": evidence,
            "requires_resampling": False
        }
