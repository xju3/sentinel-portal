import pandas as pd
import numpy as np
from scipy.stats import linregress
import json
from datetime import timedelta

class EquipmentDiagnosisSystem:
    def __init__(self, config=None):
        """
        初始化诊断系统配置（可由外部传入自定义阈值）
        """
        default_config = {
            "immediate": {"max_1h_delta": 10.0},          # 1小时允许最大突变
            "short_term": {"window_hrs": 24, "max_slope": 1.5, "max_amplitude": 15.0}, # 短期参数
            "long_term": {"window_days": 30, "baseline_shift_ratio": 0.15},            # 长期参数
            "peer_comparison": {"max_deviation_ratio": 2.5}                            # 横向对比偏离倍数
        }
        self.config = config if config else default_config

    def _preprocess_data(self, df, target_field, env_temp=None, max_physical_limit=200.0):
        """
        【数据清洗与预处理】
        1. 过滤物理上不可能的极值（如 999℃ 毛刺）
        2. 插值填补网络断线造成的数据空洞
        3. 去直流（剥离环境基准温度）
        """
        if df.empty:
            return df

        # 1. 过滤荒谬的物理极值 (将大于限值的设为 NaN，交由下一步插值处理)
        df.loc[df[target_field] > max_physical_limit, target_field] = np.nan
        
        # 2. 处理缺失值与空洞 (线性插值)
        df[target_field] = df[target_field].interpolate(method='linear')
        
        # 3. 去直流 (计算净温升)
        if env_temp is not None:
            df['net_value'] = df[target_field] - env_temp
        else:
            df['net_value'] = df[target_field] # 若无环境温度，则使用原始值
            
        return df

    def _diagnose_immediate(self, df):
        """诊断 1：即时突变 (最后 1 小时 Delta)"""
        status, desc = "NORMAL", "未发生即时突变。"
        val_str = "Delta = 0"
        
        if len(df) >= 2:
            latest_val = df['net_value'].iloc[-1]
            prev_val = df['net_value'].iloc[-2]
            delta = latest_val - prev_val
            val_str = f"Delta = {delta:.2f}"
            
            if delta > self.config['immediate']['max_1h_delta']:
                status = "ABNORMAL"
                desc = f"触发即时突变报警，1小时内急剧抬升 {delta:.2f}。"
                
        return {"status": status, "value": val_str, "desc": desc}

    def _diagnose_short_term(self, df, dynamic_upper_limit):
        """诊断 2：短期恶化 (斜率 + 区间落差)"""
        status, desc = "NORMAL", "短期趋势平稳。"
        val_str = "N/A"
        
        window_hrs = self.config['short_term']['window_hrs']
        # 截取短期窗口数据
        recent_df = df.last(f'{window_hrs}h')
        
        if len(recent_df) >= 3:
            y = recent_df['net_value'].values
            x = np.arange(len(y))
            
            # 计算斜率
            slope, _, _, _, _ = linregress(x, y)
            # 计算区间累计落差 (防阶跃突变)
            amplitude = np.max(y) - np.min(y)
            latest_val = y[-1]
            
            val_str = f"Amplitude = {amplitude:.2f}, Slope = {slope:.2f}"
            
            # 综合判定逻辑
            if amplitude > self.config['short_term']['max_amplitude']:
                status = "ABNORMAL"
                desc = f"触发阶跃式恶化报警，{window_hrs}小时内累计异常抬升达 {amplitude:.2f}。"
            elif slope > self.config['short_term']['max_slope'] and latest_val > dynamic_upper_limit:
                status = "ABNORMAL"
                desc = f"触发持续恶化报警，呈现线性抬升 (斜率 {slope:.2f}) 且突破历史 3σ 上限。"
                
        return {"status": status, "value": val_str, "desc": desc}

    def _diagnose_long_term(self, df):
        """诊断 3：长期基准漂移与离散度计算"""
        status, desc = "NORMAL", "长期基准底盘平稳。"
        val_str = "N/A"
        dynamic_upper_limit = float('inf') # 默认无上限
        
        window_days = self.config['long_term']['window_days']
        if len(df) > 24: # 至少有一天的历史数据才算
            # 计算全生命周期(本窗口内)的均值与标准差
            mu = df['net_value'].mean()
            sigma = df['net_value'].std()
            dynamic_upper_limit = mu + 3 * sigma
            
            # 近7天均值对比前期的均值
            recent_7d_mean = df.last('7d')['net_value'].mean()
            history_mean = df.loc[:df.index[-1] - timedelta(days=7)]['net_value'].mean()
            
            if pd.notna(history_mean) and history_mean > 0:
                shift_ratio = (recent_7d_mean - history_mean) / history_mean
                val_str = f"Baseline_Shift = {shift_ratio*100:.1f}%, Mu = {mu:.2f}, Sigma = {sigma:.2f}"
                
                if shift_ratio > self.config['long_term']['baseline_shift_ratio']:
                    status = "WARNING"
                    desc = f"发生慢性老化迹象，近7天基线较历史均值整体上移 {shift_ratio*100:.1f}%。"
            else:
                 val_str = f"Mu = {mu:.2f}, Sigma = {sigma:.2f}"
                 
        return {"status": status, "value": val_str, "desc": desc}, dynamic_upper_limit

    def _diagnose_peer_context(self, target_sn, df_peers, target_latest_val):
        """诊断 4：同组设备横向对比"""
        if df_peers is None or df_peers.empty:
             return {"status": "UNKNOWN", "desc": "无同组设备数据供横向比对。"}
             
        # 获取同组各设备最新值
        latest_peers = df_peers.groupby('sn')['net_value'].last()
        if len(latest_peers) < 1:
             return {"status": "UNKNOWN", "desc": "同组设备有效数据不足。"}
             
        peer_mean = latest_peers.mean()
        peer_std = latest_peers.std() if len(latest_peers) > 1 else 1.0 # 只有一台对比设备时赋予默认 std
        
        deviation_ratio = self.config['peer_comparison']['max_deviation_ratio']
        
        if abs(target_latest_val - peer_mean) > deviation_ratio * peer_std:
             return {
                 "status": "DEVIATED", 
                 "desc": f"显著偏离同组均值 ({peer_mean:.2f})，确认为单机自身异常，非环境干扰。"
             }
        else:
             return {
                 "status": "CONSISTENT", 
                 "desc": "与同组其他设备表现一致，若有异常疑似环境整体波动导致。"
             }

    def generate_report(self, target_sn, metric, df_target, df_peers=None, env_temp=None):
        """
        主干流程：组装最终 JSON 报告
        df_target: 目标设备历史 DataFrame (需包含 index 为 datetime, 及对应 metric 字段)
        df_peers: 同组设备 DataFrame
        """
        # 0. 数据预处理
        df_t = self._preprocess_data(df_target.copy(), metric, env_temp)
        if df_peers is not None:
             df_p = self._preprocess_data(df_peers.copy(), metric, env_temp)
        else:
             df_p = None
             
        latest_val = df_t['net_value'].iloc[-1]
        
        # 1. 长期诊断 (主要为了获取动态 3σ 上限)
        long_res, dynamic_upper_limit = self._diagnose_long_term(df_t)
        
        # 2. 短期诊断
        short_res = self._diagnose_short_term(df_t, dynamic_upper_limit)
        
        # 3. 即时诊断
        imm_res = self._diagnose_immediate(df_t)
        
        # 4. 横向对比
        peer_res = self._diagnose_peer_context(target_sn, df_p, latest_val)
        
        # 5. 智能汇总结论逻辑树
        health_level = "NORMAL"
        conclusion = "设备当前运行平稳，各项指标正常。"
        
        if imm_res["status"] == "ABNORMAL" or short_res["status"] == "ABNORMAL":
            health_level = "CRITICAL"
            conclusion = f"【高危预警】设备出现严重劣化。{short_res['desc']} {imm_res['desc']}"
            if peer_res["status"] == "DEVIATED":
                conclusion += " 且排除了环境干扰，强烈建议立即派单停机检查！"
        elif long_res["status"] == "WARNING":
            health_level = "WARNING"
            conclusion = f"【早期预警】{long_res['desc']} 建议在下个维保周期重点关注。"

        # 构建输出字典
        report = {
            "device_sn": target_sn,
            "metric": metric,
            "timestamp": str(df_t.index[-1]),
            "health_level": health_level,
            "diagnostics": {
                "immediate_1h": imm_res,
                "short_term_window": short_res,
                "long_term_window": long_res
            },
            "context_validation": {
                "peer_comparison": peer_res
            },
            "comprehensive_conclusion": conclusion
        }
        
        return json.dumps(report, indent=2, ensure_ascii=False)