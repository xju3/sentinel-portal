import logging
from typing import Any
import math

from app.services.context import DeviceContextService
from app.services.trend_cache import TrendCacheService

logger = logging.getLogger(__name__)

class TemperatureDiagnosis:
    """
    Temperature diagnostic engine.
    Implements a multi-tier Ratio-Based strategy with Spatial Peer Validation and 
    Noise-Resilient Linear Regression trend analysis.
    """

    @staticmethod
    def _calculate_slope(trend_data: list[dict[str, Any]]) -> float:
        """
        Calculates the slope (Rate of Change in degrees per hour) using Linear Regression (Least Squares).
        This handles sensor ADC jitter and non-monotonic fluctuations gracefully.
        Returns the slope.
        """
        if len(trend_data) < 2:
            return 0.0
            
        n = len(trend_data)
        
        # We use hours as the X-axis unit for a human-readable slope (Degrees/Hour)
        start_ts = trend_data[0]["ts_ms"]
        
        sum_x = 0.0
        sum_y = 0.0
        sum_xy = 0.0
        sum_x_squared = 0.0
        
        for point in trend_data:
            x_hours = (point["ts_ms"] - start_ts) / 3600000.0
            y_temp = point["value"]
            
            sum_x += x_hours
            sum_y += y_temp
            sum_xy += (x_hours * y_temp)
            sum_x_squared += (x_hours * x_hours)
            
        # Slope formula: (N * sum(XY) - sum(X) * sum(Y)) / (N * sum(X^2) - sum(X)^2)
        denominator = (n * sum_x_squared) - (sum_x * sum_x)
        if denominator == 0:
            return 0.0
            
        slope = ((n * sum_xy) - (sum_x * sum_y)) / denominator
        return slope

    @staticmethod
    async def analyze(device_id: str, location_id: str, current_temp: float, context: dict[str, Any]) -> dict[str, Any]:
        """
        Analyze the temperature for a specific location.
        """
        logger.info("Running temperature diagnosis for device=%s, location=%s, temp=%.2f", 
                    device_id, location_id, current_temp)

        # 1. Fetch threshold configuration from context
        thresholds = context.get("thresholds", {}).get("temperature")
        if not thresholds:
            logger.debug("No temperature thresholds configured for device=%s", device_id)
            return {"status": "ok", "reason": "no_threshold_configured"}

        max_absolute = thresholds.get("baseline", 85.0)  # absolute threshold limit
        max_delta = thresholds.get("rt_max_delta", 20.0) # max effective rise limit
        max_slope = thresholds.get("st_max_slope", 15.0) # max rate of change limit

        # 2. Phase 1: The 50% Short-Circuit Rule
        absolute_ratio = current_temp / max_absolute if max_absolute > 0 else 0
        
        if absolute_ratio < 0.50:
            logger.debug("Device=%s, location=%s absolute ratio %.2f < 50%%. Fast-fail to normal.", device_id, location_id, absolute_ratio)
            return {"status": "ok", "reason": f"normal (Absolute ratio {absolute_ratio*100:.1f}% well below 50% margin)"}

        # 3. Phase 2: Spatial Peer Validation & Delta-Based Alarming
        peer_group = context.get("peer_group")
        peer_median = 0.0
        
        if peer_group and peer_group.get("enabled"):
            peer_members = peer_group.get("members", [])
            peer_temps = []
            
            for member in peer_members:
                peer_monitoring = member.get("monitoring")
                if not peer_monitoring:
                    continue
                peer_loc = str(peer_monitoring.get("location_id"))
                if peer_loc == location_id:
                    continue 
                
                peer_trend = await TrendCacheService.get_recent_trend(peer_loc, "temperature_c")
                if peer_trend:
                    peer_temps.append(peer_trend[-1]["value"])
            
            if peer_temps:
                peer_temps.sort()
                mid = len(peer_temps) // 2
                peer_median = (peer_temps[mid] + peer_temps[~mid]) / 2.0
        
        has_peers = peer_median > 0
        ambient_temp = context.get("ambient_temperature")
        has_ambient = ambient_temp is not None
        
        if has_peers:
            effective_rise = current_temp - peer_median
        elif has_ambient:
            effective_rise = current_temp - ambient_temp
        else:
            effective_rise = 0.0
            
        delta_ratio = effective_rise / max_delta if max_delta > 0 and (has_peers or has_ambient) else 0.0
        
        status = "ok"
        severity = "info"
        reason = f"Running normally at {current_temp:.1f}C"
        
        if (has_peers or has_ambient) and max_delta > 0:
            if delta_ratio > 0.90:
                status = "alarm"
                severity = "critical"
                reason = f"Danger: Temperature rise {effective_rise:.1f}C is at {delta_ratio*100:.1f}% of delta limit!"
            elif delta_ratio > 0.80:
                status = "alarm"
                severity = "warning"
                reason = f"Warning: Temperature rise {effective_rise:.1f}C is {delta_ratio*100:.1f}% of delta limit."
            elif delta_ratio > 0.70:
                status = "alarm"
                severity = "abnormal"
                reason = f"Abnormal: Operating margin shrinking (delta {delta_ratio*100:.1f}%)."
            elif delta_ratio >= 0.50:
                status = "alarm"
                severity = "attention"
                reason = f"Attention: Device warming up (delta {delta_ratio*100:.1f}%)."
        else:
            if absolute_ratio > 0.90:
                status = "alarm"
                severity = "critical"
                reason = f"Danger: Temperature {current_temp:.1f}C is at {absolute_ratio*100:.1f}% of limit!"
            elif absolute_ratio > 0.80:
                status = "alarm"
                severity = "warning"
                reason = f"Warning: Temperature {current_temp:.1f}C is {absolute_ratio*100:.1f}% of limit."
            elif absolute_ratio > 0.70:
                status = "alarm"
                severity = "abnormal"
                reason = f"Abnormal: Operating margin shrinking ({absolute_ratio*100:.1f}%)."
            elif absolute_ratio >= 0.50:
                status = "alarm"
                severity = "attention"
                reason = f"Attention: Device warming up ({absolute_ratio*100:.1f}%)."

        if has_peers and absolute_ratio > 0.95 and severity not in ["critical", "warning"]:
            status = "alarm"
            severity = "warning"
            reason = f"Warning: Absolute temperature {current_temp:.1f}C is near ceiling limit!"

        # 4. Phase 3: Trend Override via Linear Regression
        trend_data = await TrendCacheService.get_recent_trend(location_id, "temperature_c")
        
        if len(trend_data) >= 6: 
            slope_deg_per_hour = TemperatureDiagnosis._calculate_slope(trend_data)
            
            if slope_deg_per_hour > max_slope:
                logger.warning("Spike detected! Slope: %.2f deg/hour (limit: %.2f)", slope_deg_per_hour, max_slope)
                if severity in ["info", "attention", "abnormal"]:
                    status = "alarm"
                    severity = "warning"
                    reason = f"Escalated to Warning due to violent spike: {slope_deg_per_hour:.1f}C/hour! Current temp: {current_temp:.1f}C"
        
        return {
            "status": status,
            "severity": severity,
            "reason": reason,
            "ratio": absolute_ratio,
            "delta_ratio": delta_ratio,
            "peer_median": peer_median,
            "effective_rise": effective_rise
        }
