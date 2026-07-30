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
    def _finish_evidence(
        evidence: dict[str, Any],
        *,
        severity: str,
        primary_rule: str | None,
    ) -> dict[str, Any]:
        evidence["result"] = {
            "level": {
                "ok": 0,
                "normal": 0,
                "info": 0,
                "attention": 1,
                "abnormal": 2,
                "warning": 3,
                "critical": 4,
            }.get(severity, 0),
            "primary_rule": primary_rule,
            "triggered_rules": [
                check["code"]
                for check in evidence["checks"]
                if check.get("triggered")
            ],
        }
        return evidence

    @staticmethod
    def _window_summary(
        trend_data: list[dict[str, Any]],
        *,
        hours: int,
        current_val: float,
        current_ts_ms: int | None,
    ) -> dict[str, Any]:
        values = [float(point["value"]) for point in trend_data]
        if not values:
            values = [current_val]
        return {
            "hours": hours,
            "from_ts_ms": trend_data[0]["ts_ms"] if trend_data else current_ts_ms,
            "to_ts_ms": current_ts_ms,
            "sample_count": len(trend_data),
            "min": min(values),
            "max": max(values),
        }

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

        evidence: dict[str, Any] = {
            "schema_version": 2,
            "fault_type": "vibration",
            "current": max_rms_vel,
            "healthy_median": healthy_median,
            "context": {
                "current": max_rms_vel,
                "healthy_median": healthy_median,
                "baseline": baseline,
                "unit": "mm/s",
            },
            "checks": [],
            "peer": None,
        }
        
        # Base Ratio calculation: (current - healthy) / (baseline - healthy)
        if baseline > healthy_median:
            ratio = (max_rms_vel - healthy_median) / (baseline - healthy_median)
        else:
            ratio = 0.0
        ratio = max(0.0, ratio) # 防止当前值低于健康中位数时出现负数
        
        evidence["vibration_budget_ratio"] = round(ratio, 4)
        evidence["context"]["budget_ratio"] = round(ratio, 4)
        context_severity = VibrationDiagnosis._get_severity_from_ratio(ratio)

        # 1. Absolute Baseline Check
        baseline_triggered = max_rms_vel >= baseline
        evidence["checks"].append(
            {
                "code": "vibration.absolute_baseline",
                "label": "绝对振动阈值",
                "observed": max_rms_vel,
                "operator": ">=",
                "threshold": baseline,
                "unit": "mm/s",
                "triggered": baseline_triggered,
            }
        )
        if baseline_triggered:
            return {
                "status": "alarm",
                "severity": "critical",
                "reason": f"Critical: Absolute vibration {max_rms_vel:.2f} mm/s exceeded baseline {baseline} mm/s!",
                "evidence": VibrationDiagnosis._finish_evidence(
                    evidence,
                    severity="critical",
                    primary_rule="vibration.absolute_baseline",
                ),
                "requires_resampling": True
            }
            
        # Warning Zone baseline check
        warning_zone_triggered = ratio >= 0.70
        evidence["checks"].append(
            {
                "code": "vibration.warning_zone",
                "label": "振动阈值接近度",
                "observed": round(ratio, 4),
                "operator": ">=",
                "threshold": 0.70,
                "unit": "ratio",
                "triggered": warning_zone_triggered,
            }
        )
        if warning_zone_triggered:
            return {
                "status": "alarm",
                "severity": "warning",
                "reason": f"Warning: Vibration {max_rms_vel:.2f} mm/s reached {ratio*100:.1f}% of baseline.",
                "evidence": VibrationDiagnosis._finish_evidence(
                    evidence,
                    severity="warning",
                    primary_rule="vibration.warning_zone",
                ),
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
            mutation_triggered = mutation > rt_max_delta
            evidence["checks"].append(
                {
                    "code": "vibration.realtime_mutation",
                    "label": "实时振动突变",
                    "observed": mutation,
                    "operator": ">",
                    "threshold": rt_max_delta,
                    "unit": "mm/s",
                    "triggered": mutation_triggered,
                }
            )
            if mutation_triggered:
                return {
                    "status": "alarm",
                    "severity": "warning",
                    "reason": f"Warning: Real-time mutation {mutation:.2f} mm/s exceeds limit {rt_max_delta} mm/s!",
                    "evidence": VibrationDiagnosis._finish_evidence(
                        evidence,
                        severity="warning",
                        primary_rule="vibration.realtime_mutation",
                    ),
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
                peer_deviation = abs(max_rms_vel - peer_median)
                peer_triggered = peer_deviation > 5.0
                evidence["peer"] = {
                    "median": peer_median,
                    "deviation": peer_deviation,
                    "threshold": 5.0,
                    "sample_count": len(peer_values),
                }
                evidence["checks"].append(
                    {
                        "code": "vibration.peer_deviation",
                        "label": "同类设备振动偏差",
                        "observed": peer_deviation,
                        "operator": ">",
                        "threshold": 5.0,
                        "unit": "mm/s",
                        "triggered": peer_triggered,
                    }
                )
                if peer_triggered:
                    severity = VibrationDiagnosis._escalate(severity, "abnormal")
                    alarm_reason = f"Peer deviation: current {max_rms_vel:.2f} mm/s differs from peer median {peer_median:.2f} mm/s."
                    
                    return {
                        "status": "alarm",
                        "severity": severity,
                        "reason": alarm_reason,
                        "evidence": VibrationDiagnosis._finish_evidence(
                            evidence,
                            severity=severity,
                            primary_rule="vibration.peer_deviation",
                        ),
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
            st_window = VibrationDiagnosis._window_summary(
                st_trend,
                hours=24,
                current_val=max_rms_vel,
                current_ts_ms=current_ts_ms,
            )
            evidence["checks"].extend(
                [
                    {
                        "code": "vibration.short_term_slope",
                        "label": "24小时振动斜率",
                        "observed": round(st_slope, 4),
                        "operator": "abs >",
                        "threshold": st_max_slope,
                        "unit": "mm/s/hour",
                        "triggered": abs(st_slope) > st_max_slope,
                        "window": st_window,
                    },
                    {
                        "code": "vibration.short_term_amplitude",
                        "label": "24小时振动振幅",
                        "observed": round(st_amplitude, 4),
                        "operator": ">",
                        "threshold": st_max_amplitude,
                        "unit": "mm/s",
                        "triggered": st_amplitude > st_max_amplitude,
                        "window": st_window,
                    },
                ]
            )
            
            if abs(st_slope) > st_max_slope or st_amplitude > st_max_amplitude:
                severity = VibrationDiagnosis._escalate(severity, context_severity)
                alarm_reason = "Violated Short-Term trend."
                
            mt_slope = VibrationDiagnosis._calculate_slope(mt_trend)
            mt_amplitude = VibrationDiagnosis._calculate_amplitude(mt_trend, max_rms_vel)
            evidence["mt_slope"] = round(mt_slope, 4)
            evidence["mt_amplitude"] = round(mt_amplitude, 4)
            mt_window = VibrationDiagnosis._window_summary(
                mt_trend,
                hours=72,
                current_val=max_rms_vel,
                current_ts_ms=current_ts_ms,
            )
            evidence["checks"].extend(
                [
                    {
                        "code": "vibration.middle_term_slope",
                        "label": "72小时振动斜率",
                        "observed": round(mt_slope, 4),
                        "operator": "abs >",
                        "threshold": mt_max_slope,
                        "unit": "mm/s/hour",
                        "triggered": abs(mt_slope) > mt_max_slope,
                        "window": mt_window,
                    },
                    {
                        "code": "vibration.middle_term_amplitude",
                        "label": "72小时振动振幅",
                        "observed": round(mt_amplitude, 4),
                        "operator": ">",
                        "threshold": mt_max_amplitude,
                        "unit": "mm/s",
                        "triggered": mt_amplitude > mt_max_amplitude,
                        "window": mt_window,
                    },
                ]
            )
            
            if not alarm_reason and (abs(mt_slope) > mt_max_slope or mt_amplitude > mt_max_amplitude):
                severity = VibrationDiagnosis._escalate(severity, context_severity)
                alarm_reason = "Violated Middle-Term trend."

        if alarm_reason:
            if severity in {"ok", "normal", "info"}:
                severity = "attention"
            return {
                "status": "alarm",
                "severity": severity,
                "reason": alarm_reason,
                "evidence": VibrationDiagnosis._finish_evidence(
                    evidence,
                    severity=severity,
                    primary_rule=next(
                        (
                            check["code"]
                            for check in evidence["checks"]
                            if check.get("triggered")
                        ),
                        None,
                    ),
                ),
                "requires_resampling": False
            }

        return {
            "status": "ok",
            "severity": "info",
            "reason": f"Running normally at {max_rms_vel:.2f} mm/s",
            "evidence": VibrationDiagnosis._finish_evidence(
                evidence,
                severity="info",
                primary_rule=None,
            ),
            "requires_resampling": False
        }
