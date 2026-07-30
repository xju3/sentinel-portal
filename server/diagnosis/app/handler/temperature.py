import logging
from typing import Any
import time

from app.services.context import DeviceContextService
from pub.services.trend_cache import TrendCacheService
from app.services.baseline_service import BaselineService

logger = logging.getLogger(__name__)

class TemperatureDiagnosis:
    """
    Temperature diagnostic engine.
    
    环境温度的唯一使命：诊断门神 (Gateway Gatekeeper)
    如果 `当前温度 * 1.1 <= 所在地环境温度`，则直接判定设备温度正常，彻底终止后续所有复杂的计算。
    
    动态定级基准：热负荷预算占比 (Thermal Budget Ratio)
    ratio = (当前温度 - 环境温度) / (baseline - 环境温度)
    以此占比划分区间：<10% (Info), 10~20% (Attention), 20~40% (Abnormal), 40~70% (Warning), >=70% (Critical)。
    所有的历史趋势违规（短期/中期斜率与振幅）以及横向对等组比较违规，均由该 ratio 对应的区间决定其严重程度。
    
    维度一：设备自身温度与历史数据的纵向比对 (Vertical Strategy)
    1. 不可突破的红线 (Absolute Baseline)：
       直接对比 SensorThreshold.baseline。触碰此线，立刻报出顶级 Critical 告警。
    2. 实时突变拦截 (Real-Time Mutation)：
       与上一次记录相比，差值绝对值不得超过 rt_max_delta。硬件级异常，独立报 Warning。
    3. 短期趋势约束 (Short-Term: 24小时内)：
       振幅约束与斜率约束。超标时，其告警级别取决于当前的 Thermal Budget Ratio。
    4. 中期趋势约束 (Middle-Term: 72小时内)：
       振幅约束与斜率约束。超标时，其告警级别取决于当前的 Thermal Budget Ratio。
       
    维度二：基于同规格对等组的横向异常检测 (Horizontal Peer Strategy)
    如果偏离中位数超过阈值，报出的严重程度同样由 Thermal Budget Ratio 决定。
    """

    @staticmethod
    def _calculate_slope(trend_data: list[dict[str, Any]]) -> float:
        if len(trend_data) < 2:
            return 0.0
            
        n = len(trend_data)
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
            
        denominator = (n * sum_x_squared) - (sum_x * sum_x)
        if denominator == 0:
            return 0.0
            
        return ((n * sum_xy) - (sum_x * sum_y)) / denominator

    @staticmethod
    def _calculate_amplitude(trend_data: list[dict[str, Any]], current_temp: float) -> float:
        if not trend_data:
            return 0.0
        temps = [p["value"] for p in trend_data]
        temps.append(current_temp)
        return max(temps) - min(temps)

    @staticmethod
    def _get_severity_from_ratio(ratio: float) -> str:
        """根据热负荷预算占比计算告警严重程度"""
        if ratio >= 0.70: return "critical"
        if ratio >= 0.40: return "warning"
        if ratio >= 0.20: return "abnormal"
        if ratio >= 0.10: return "attention"
        return "attention" # 最低保证一个 attention，因为既然违规了，哪怕在正常区间也应提醒客户

    @staticmethod
    def _escalate(current_severity: str, new_severity: str) -> str:
        levels = {"ok": 0, "info": 0, "attention": 1, "abnormal": 2, "warning": 3, "critical": 4}
        if levels.get(new_severity, 0) > levels.get(current_severity, 0):
            return new_severity
        return current_severity

    @staticmethod
    def _window_summary(
        trend_data: list[dict[str, Any]],
        *,
        hours: int,
        current_temp: float,
        current_ts_ms: int,
    ) -> dict[str, Any]:
        values = [float(point["value"]) for point in trend_data]
        if not values:
            values = [current_temp]
        return {
            "hours": hours,
            "from_ts_ms": trend_data[0]["ts_ms"] if trend_data else current_ts_ms,
            "to_ts_ms": current_ts_ms,
            "sample_count": len(trend_data),
            "min": min(values),
            "max": max(values),
        }

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
    async def analyze(
        device_id: str,
        location_id: str,
        current_temp: float,
        context: dict[str, Any],
        current_ts_ms: int | None = None,
    ) -> dict[str, Any]:
        logger.info("Running temperature diagnosis for device=%s, location=%s, temp=%.2f", 
                    device_id, location_id, current_temp)

        # 1. Fetch threshold configuration
        thresholds = context.get("thresholds", {}).get("temperature", {})
        baseline = float(thresholds.get("baseline", 85.0))
        rt_max_delta = float(thresholds.get("rt_max_delta", 15.0))
        st_max_amplitude = float(thresholds.get("st_max_amplitude", 20.0))
        st_max_slope = float(thresholds.get("st_max_slope", 10.0))
        mt_max_amplitude = float(thresholds.get("mt_max_amplitude", 25.0))
        mt_max_slope = float(thresholds.get("mt_max_slope", 2.0))

        ambient_temp = context.get("ambient_temperature")
        evidence: dict[str, Any] = {
            "schema_version": 2,
            "fault_type": "temperature",
            "current": current_temp,
            "ambient": ambient_temp,
            "context": {
                "current": current_temp,
                "ambient": ambient_temp,
                "baseline": baseline,
                "unit": "°C",
            },
            "checks": [],
            "peer": None,
        }

        # --- PRE-GATEWAY FAULT CHECKS ---
        
        # 1. Absolute Baseline (Never allowed to exceed)
        baseline_triggered = current_temp >= baseline
        evidence["checks"].append(
            {
                "code": "temperature.absolute_baseline",
                "label": "绝对温度阈值",
                "observed": current_temp,
                "operator": ">=",
                "threshold": baseline,
                "unit": "°C",
                "triggered": baseline_triggered,
            }
        )
        if baseline_triggered:
            return {
                "status": "alarm",
                "severity": "critical",
                "reason": f"Critical: Absolute temperature {current_temp:.1f}°C exceeded baseline {baseline}°C!",
                "evidence": TemperatureDiagnosis._finish_evidence(
                    evidence,
                    severity="critical",
                    primary_rule="temperature.absolute_baseline",
                ),
            }

        trend_data = await TrendCacheService.get_recent_trend(location_id, "temperature_c")
        if current_ts_ms is not None:
            trend_data = [
                point for point in trend_data
                if point["ts_ms"] <= current_ts_ms
            ]
        previous_trend = [
            point for point in trend_data
            if current_ts_ms is None or point["ts_ms"] < current_ts_ms
        ]
        
        # 2. Real-Time Mutation (Hardware fault detection)
        if previous_trend:
            last_temp = previous_trend[-1]["value"]
            mutation = abs(current_temp - last_temp)
            evidence["mutation"] = mutation
            evidence["last_temp"] = last_temp
            mutation_triggered = mutation > rt_max_delta
            evidence["checks"].append(
                {
                    "code": "temperature.realtime_mutation",
                    "label": "实时温度突变",
                    "observed": mutation,
                    "operator": ">",
                    "threshold": rt_max_delta,
                    "unit": "°C",
                    "triggered": mutation_triggered,
                }
            )
            if mutation_triggered:
                return {
                    "status": "alarm",
                    "severity": "warning",
                    "reason": f"Warning: Real-time mutation {mutation:.1f}°C exceeds limit {rt_max_delta}°C!",
                    "evidence": TemperatureDiagnosis._finish_evidence(
                        evidence,
                        severity="warning",
                        primary_rule="temperature.realtime_mutation",
                    ),
                }

        # 3. Gateway Gatekeeper
        if ambient_temp is not None and (current_temp * 1.1) <= ambient_temp:
            logger.info("Device=%s current_temp=%.2f * 1.1 is below ambient=%.2f. Fast-fail to normal.", device_id, current_temp, ambient_temp)
            evidence["gateway"] = "passed"
            return {
                "status": "ok",
                "severity": "info",
                "reason": f"Normal: Temperature {current_temp:.1f}°C is within ambient baseline.",
                "evidence": TemperatureDiagnosis._finish_evidence(
                    evidence,
                    severity="info",
                    primary_rule=None,
                ),
            }

        status = "ok"
        severity = "info"
        reason = f"Running normally at {current_temp:.1f}°C"

        # --- THERMAL BUDGET RATIO ---
        # 计算热负荷预算占比作为定级系数
        ratio = 0.0
        if ambient_temp is not None and baseline > ambient_temp:
            ratio = (current_temp - ambient_temp) / (baseline - ambient_temp)
        
        evidence["thermal_budget_ratio"] = ratio
        evidence["context"]["budget_ratio"] = ratio
        context_severity = TemperatureDiagnosis._get_severity_from_ratio(ratio)

        # --- VERTICAL STRATEGY ---

        # Filter trend data into 24h and 72h windows
        now_ms = current_ts_ms if current_ts_ms is not None else int(time.time() * 1000)
        ms_24h = 24 * 3600 * 1000
        ms_72h = 72 * 3600 * 1000
        
        st_trend = [p for p in trend_data if now_ms - p["ts_ms"] <= ms_24h]
        mt_trend = [p for p in trend_data if now_ms - p["ts_ms"] <= ms_72h]

        # 4. Short-Term (24h)
        st_slope = TemperatureDiagnosis._calculate_slope(st_trend)
        st_amplitude = TemperatureDiagnosis._calculate_amplitude(st_trend, current_temp)
        evidence.update({"st_slope": st_slope, "st_amplitude": st_amplitude})
        st_window = TemperatureDiagnosis._window_summary(
            st_trend,
            hours=24,
            current_temp=current_temp,
            current_ts_ms=now_ms,
        )
        evidence["checks"].extend(
            [
                {
                    "code": "temperature.short_term_slope",
                    "label": "24小时升温斜率",
                    "observed": st_slope,
                    "operator": ">",
                    "threshold": st_max_slope,
                    "unit": "°C/hour",
                    "triggered": st_slope > st_max_slope,
                    "window": st_window,
                },
                {
                    "code": "temperature.short_term_amplitude",
                    "label": "24小时温度振幅",
                    "observed": st_amplitude,
                    "operator": ">",
                    "threshold": st_max_amplitude,
                    "unit": "°C",
                    "triggered": st_amplitude > st_max_amplitude,
                    "window": st_window,
                },
            ]
        )
        
        if st_slope > st_max_slope:
            status = "alarm"
            severity = TemperatureDiagnosis._escalate(severity, context_severity)
            reason = f"Violated Short-Term Slope: {st_slope:.1f}°C/hour (limit {st_max_slope}). Dynamic Level: {severity}"
        elif st_amplitude > st_max_amplitude:
            status = "alarm"
            severity = TemperatureDiagnosis._escalate(severity, context_severity)
            reason = f"Violated Short-Term Amplitude: {st_amplitude:.1f}°C exceeds {st_max_amplitude}°C. Dynamic Level: {severity}"

        # 5. Middle-Term (72h)
        mt_slope = TemperatureDiagnosis._calculate_slope(mt_trend)
        mt_amplitude = TemperatureDiagnosis._calculate_amplitude(mt_trend, current_temp)
        evidence.update({"mt_slope": mt_slope, "mt_amplitude": mt_amplitude})
        mt_window = TemperatureDiagnosis._window_summary(
            mt_trend,
            hours=72,
            current_temp=current_temp,
            current_ts_ms=now_ms,
        )
        evidence["checks"].extend(
            [
                {
                    "code": "temperature.middle_term_slope",
                    "label": "72小时升温斜率",
                    "observed": mt_slope,
                    "operator": ">",
                    "threshold": mt_max_slope,
                    "unit": "°C/hour",
                    "triggered": mt_slope > mt_max_slope,
                    "window": mt_window,
                },
                {
                    "code": "temperature.middle_term_amplitude",
                    "label": "72小时温度振幅",
                    "observed": mt_amplitude,
                    "operator": ">",
                    "threshold": mt_max_amplitude,
                    "unit": "°C",
                    "triggered": mt_amplitude > mt_max_amplitude,
                    "window": mt_window,
                },
            ]
        )
        
        if status == "ok":
            if mt_slope > mt_max_slope:
                status = "alarm"
                severity = TemperatureDiagnosis._escalate(severity, context_severity)
                reason = f"Violated Mid-Term Slope: {mt_slope:.2f}°C/hour (limit {mt_max_slope}). Dynamic Level: {severity}"
            elif mt_amplitude > mt_max_amplitude:
                status = "alarm"
                severity = TemperatureDiagnosis._escalate(severity, context_severity)
                reason = f"Violated Mid-Term Amplitude: {mt_amplitude:.1f}°C exceeds {mt_max_amplitude}°C. Dynamic Level: {severity}"

        # --- HORIZONTAL STRATEGY ---
        peer_group = context.get("peer_group", {})
        if peer_group.get("enabled"):
            peer_members = peer_group.get("members", [])
            peer_temps = []
            
            for member in peer_members:
                peer_loc = str(member.get("location_id"))
                if peer_loc == location_id:
                    continue 
                
                peer_trend = await TrendCacheService.get_recent_trend(peer_loc, "temperature_c")
                if peer_trend and len(peer_trend) > 0:
                    peer_temps.append(peer_trend[-1]["value"])
            
            if peer_temps:
                peer_temps.sort()
                mid = len(peer_temps) // 2
                peer_median = (peer_temps[mid] + peer_temps[~mid]) / 2.0
                evidence["peer_median"] = peer_median
                
                peer_deviation = current_temp - peer_median
                peer_threshold = 10.0 if peer_deviation > 10.0 else 5.0
                peer_triggered = peer_deviation > 10.0 or (
                    peer_deviation > 5.0 and severity == "info"
                )
                evidence["peer"] = {
                    "median": peer_median,
                    "deviation": peer_deviation,
                    "threshold": peer_threshold,
                    "sample_count": len(peer_temps),
                }
                evidence["checks"].append(
                    {
                        "code": "temperature.peer_deviation",
                        "label": "同类设备温度偏差",
                        "observed": peer_deviation,
                        "operator": ">",
                        "threshold": peer_threshold,
                        "unit": "°C",
                        "triggered": peer_triggered,
                    }
                )
                if peer_deviation > 10.0:
                    status = "alarm"
                    severity = TemperatureDiagnosis._escalate(severity, context_severity)
                    # For huge deviations, maybe bump up one extra level? Let's stick to context_severity as requested.
                    reason = f"Horizontal Violation: Deviates {peer_deviation:.1f}°C from peer median {peer_median:.1f}°C. Dynamic Level: {severity}"
                elif peer_deviation > 5.0 and severity == "info":
                    status = "alarm"
                    severity = TemperatureDiagnosis._escalate(severity, context_severity)
                    reason = f"Horizontal Violation: Deviates {peer_deviation:.1f}°C from peer median {peer_median:.1f}°C. Dynamic Level: {severity}"

        return {
            "status": status,
            "severity": severity,
            "reason": reason,
            "evidence": TemperatureDiagnosis._finish_evidence(
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
        }
