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

        max_absolute = thresholds.get("rt_max_delta", 85.0)  # absolute threshold limit

        # 2. Phase 1: The 50% Short-Circuit Rule (极速短路优化)
        ratio = current_temp / max_absolute
        
        if ratio < 0.50:
            # Fundamentally safe. Skip heavy ZSET fetches and peer validations!
            logger.debug("Device=%s, location=%s ratio %.2f < 50%%. Fast-fail to normal.", device_id, location_id, ratio)
            return {"status": "ok", "reason": f"normal (Ratio {ratio*100:.1f}% well below 50% margin)"}

        # --- If we reach here, the machine is warming up. We must fetch trends and peers. ---

        # 3. Phase 2: Spatial Peer Validation & Ratio-Based Alarming
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
                    continue # Skip self
                
                # Instantly get current state of peer
                peer_trend = await TrendCacheService.get_recent_trend(peer_loc, "temperature_c")
                if peer_trend:
                    peer_temps.append(peer_trend[-1]["value"])
            
            if peer_temps:
                peer_temps.sort()
                mid = len(peer_temps) // 2
                peer_median = (peer_temps[mid] + peer_temps[~mid]) / 2.0
        
        # Calculate Effective Rise (subtract ambient baseline if peers exist)
        # If no peers, effective_rise is just current_temp
        effective_rise = current_temp - peer_median if peer_median > 0 else current_temp
        
        # Determine base severity from Ratio
        status = "ok"
        severity = "info"
        reason = f"Running normally at {current_temp:.1f}C"
        
        if ratio > 0.90:
            status = "alarm"
            severity = "critical"
            reason = f"Danger: Temperature {current_temp:.1f}C is at {ratio*100:.1f}% of failure limit!"
        elif ratio > 0.80:
            status = "alarm"
            severity = "warning"
            reason = f"Warning: Temperature {current_temp:.1f}C is {ratio*100:.1f}% of limit."
        elif ratio > 0.70:
            status = "alarm"
            severity = "abnormal"
            reason = f"Abnormal: Operating margin shrinking ({ratio*100:.1f}%)."
        elif ratio >= 0.50:
            status = "alarm"
            severity = "attention"
            reason = f"Attention: Device warming up ({ratio*100:.1f}%)."

        # 4. Phase 3: Trend Override via Linear Regression
        # If the machine is at <90% ratio, but it's spiking violently, we escalate the severity.
        trend_data = await TrendCacheService.get_recent_trend(location_id, "temperature_c")
        
        if len(trend_data) >= 6: # Need enough points for a meaningful regression
            slope_deg_per_hour = TemperatureDiagnosis._calculate_slope(trend_data)
            
            # Very fast rise: e.g. > 15 degrees per hour
            if slope_deg_per_hour > 15.0:
                logger.warning("Spike detected! Slope: %.2f deg/hour", slope_deg_per_hour)
                if severity in ["attention", "abnormal"]:
                    status = "alarm"
                    severity = "warning"  # Escalate!
                    reason = f"Escalated to Warning due to violent spike: {slope_deg_per_hour:.1f}C/hour! Current temp: {current_temp:.1f}C"
        
        return {
            "status": status,
            "severity": severity,
            "reason": reason,
            "ratio": ratio,
            "peer_median": peer_median,
            "effective_rise": effective_rise
        }
