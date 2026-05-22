import logging
import numpy as np
from scipy.stats import linregress
from typing import Dict, Any, List

from app.clients.redis import redis_client

logger = logging.getLogger(__name__)

class PatrolDiagnosticEngine:
    def __init__(self):
        # 诊断配置阈值 (实际应用中建议移至集中式 Config)
        self.config = {
            "real_time": {"max_delta": 2.0},
            # 短期参数 (2h, 4h, 8h, 16h, 24h)
            "short_term": {"max_slope": 1.5, "max_amplitude": 15.0},
            # 中期参数 (24h/1d, 48h/2d, 72h/3d) - 允许的斜率更平缓，主要抓慢性积累
            "medium_term": {"max_slope": 0.5, "max_amplitude": 20.0},
            "default_baseline": 85.0 # 缺乏长期基准时的硬性死线
        }
        
        # 定义需要遍历的诊断窗口 (小时/数据点数)
        self.short_windows = [2, 4, 8, 16]
        self.medium_windows = [24, 48, 72]

    def _get_dynamic_baseline(self, sn: str) -> float:
        """获取长期动态基准 (需对接凌晨离线任务生成的 Redis Hash，暂返回默认值)"""
        return self.config["default_baseline"]

    def _calc_trend(self, data_slice: List[float]) -> tuple:
        """
        计算指定时间切片内的斜率和累计落差
        注意：传入的 data_slice 是时间倒序(最新->最老)，需要反转为时间正序(最老->最新)来算斜率
        """
        y = np.array(data_slice[::-1]) 
        amplitude = np.max(y) - np.min(y)
        x = np.arange(len(y))
        
        # 至少需要 3 个点拟合斜率才具有统计学意义，否则设为 0
        if len(y) >= 3:
            slope, _, _, _, _ = linregress(x, y)
        else:
            slope = y[-1] - y[0] # 若只有2个点，斜率即为首尾差
            
        return slope, amplitude

    # 状态等级映射: 0=正常, 1=需关注, 2=严重异常, -1=数据不足
    STATUS_MAP = {
        "NORMAL": 0,
        "WARNING": 1,
        "CRITICAL": 2,
        "INSUFFICIENT_DATA": -1,
    }

    def _diagnose_windows(
        self,
        values: List[float],
        queue_len: int,
        freq: float,
        windows: List[int],
        config_key: str,
        label_map: dict,
        latest_val: float,
        dynamic_baseline: float,
    ) -> List[dict]:
        """通用多窗口诊断逻辑（短期/中期共用）

        Args:
            values: 目标字段值列表（时间倒序）
            queue_len: 队列实际长度
            freq: 数据密度系数
            windows: 窗口定义列表（如 [2,4,8,16] 或 [24,48,72]）
            config_key: 配置键名（"short_term" 或 "medium_term"）
            label_map: 窗口值到显示标签的映射
            latest_val: 最新值
            dynamic_baseline: 动态基准线

        Returns:
            诊断详情列表
        """
        details = []
        for w in windows:
            need_points = int(w * freq)
            if queue_len < need_points:
                details.append({
                    "window": label_map.get(w, f"{w}h"),
                    "status": self.STATUS_MAP["INSUFFICIENT_DATA"],
                    "metric": "N/A",
                    "desc": f"数据不足 (需≥{need_points}点，当前{queue_len}点)"
                })
                continue

            slope, amp = self._calc_trend(values[:need_points])
            w_status = self.STATUS_MAP["NORMAL"]

            if amp > self.config[config_key]["max_amplitude"]:
                w_status = self.STATUS_MAP["CRITICAL"]
            elif slope > self.config[config_key]["max_slope"] and latest_val > dynamic_baseline:
                w_status = self.STATUS_MAP["WARNING"]

            is_medium = config_key == "medium_term"
            details.append({
                "window": label_map.get(w, f"{w}h"),
                "status": w_status,
                "metric": f"Slope={slope:.2f}, Amp={amp:.2f}",
                "desc": "大幅波动" if w_status == self.STATUS_MAP["CRITICAL"]
                        else ("持续上升" if w_status == self.STATUS_MAP["WARNING"]
                        else ("基线平稳" if is_medium else "平稳"))
            })
        return details

    async def run_diagnostics(self, sn: str, target_field: str = "temperature") -> Dict[str, Any]:
        """
        执行 1+5+3 瀑布式多尺度诊断
        """
        
        queue = await redis_client.get_queue(sn)
        queue_len = len(queue)
        freq = queue_len / 72
        
        # 初始化报告基础结构
        report = {
            "sn": sn,
            "metric": target_field,
            "health_status": 0,
            "comprehensive_conclusion": "设备当前运行平稳",
            "diagnostic_details": []
        }

        # 数据极度不足，无法进行任何诊断
        if queue_len < 2:
            report["comprehensive_conclusion"] = f"数据不足 (仅 {queue_len} 点)，无法进行任何诊断。"
            return report

        # 提取目标字段值列表 (时间倒序：[最新, 前1h, 前2h...])
        values = [item[target_field] for item in queue]
        latest_val = values[0]
        dynamic_baseline = self._get_dynamic_baseline(sn)
        
        # ==========================================
        # 1. 实时诊断 (Real-time: 1h / 2点)
        # ==========================================
        if queue_len < 2:
            report["diagnostic_details"].append({
                "window": "1h", "status": self.STATUS_MAP["INSUFFICIENT_DATA"],
                "metric": "N/A", "desc": f"数据不足 (需≥2点，当前{queue_len}点)"
            })
        else:
            delta = latest_val - values[1]
            rt_status = self.STATUS_MAP["NORMAL"]
            rt_desc = "正常"
            if delta > self.config["real_time"]["max_delta"]:
                rt_status = self.STATUS_MAP["CRITICAL"]
                rt_desc = "明显抬升"
                report["health_status"] = max(report["health_status"], rt_status)
                
            report["diagnostic_details"].append({
                "window": "1h",
                "status": rt_status,
                "metric": f"Delta = {delta:.2f}",
                "desc": rt_desc
            })

        # ==========================================
        # 2. 短期诊断 (Short-term: 2, 4, 8, 16h)
        # ==========================================
        short_details = self._diagnose_windows(
            values, queue_len, freq,
            self.short_windows, "short_term",
            {w: f"{w}h" for w in self.short_windows},
            latest_val, dynamic_baseline
        )
        report["diagnostic_details"].extend(short_details)
        for item in short_details:
            if item["status"] > 0:
                report["health_status"] = max(report["health_status"], item["status"])

        # ==========================================
        # 3. 中期诊断 (Medium-term: 24h/1d, 48h/2d, 72h/3d)
        # ==========================================
        medium_details = self._diagnose_windows(
            values, queue_len, freq,
            self.medium_windows, "medium_term",
            {24: "1d", 48: "2d", 72: "3d"},
            latest_val, dynamic_baseline
        )
        report["diagnostic_details"].extend(medium_details)
        for item in medium_details:
            if item["status"] > 0:
                report["health_status"] = max(report["health_status"], item["status"])

        # ==========================================
        # 4. 汇总结论生成
        # ==========================================
        # 收集各诊断阶段出现的异常 (status > 0 即为异常)
        abnormal_stages = []
        for item in report["diagnostic_details"]:
            if item["status"] > 0:
                abnormal_stages.append(f"{item['window']}: {item['desc']} ({item['metric']})")

        # 组装简洁结论
        if report["health_status"] == self.STATUS_MAP["CRITICAL"]:
            report["comprehensive_conclusion"] = "🔴 严重异常: " + "; ".join(abnormal_stages)
            
        elif report["health_status"] == self.STATUS_MAP["WARNING"]:
            report["comprehensive_conclusion"] = "🟡 需关注: " + "; ".join(abnormal_stages)
            
        else:
            report["comprehensive_conclusion"] = "🟢 运行正常"

        return report 

# 实例化全局引擎
patrol_diagnostic_engine = PatrolDiagnosticEngine()
