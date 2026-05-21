import pandas as pd
import numpy as np
from scipy.stats import linregress
from influxdb_client import InfluxDBClient

class PatrolInspection:
    def __init__(self, url, token, org, bucket):
        self.client = InfluxDBClient(url=url, token=token, org=org)
        self.query_api = self.client.query_api()
        self.bucket = bucket

    def fetch_group_data(self, measurement, group_id, hours=24):
        """
        按 group_id 拉取整组设备的数据，为横向对比做准备
        """
        query = f'''
        from(bucket: "{self.bucket}")
          |> range(start: -{hours}h)
          |> filter(fn: (r) => r["_measurement"] == "{measurement}")
          |> filter(fn: (r) => r["group_id"] == "{group_id}")
          |> filter(fn: (r) => r["_field"] == "temperature" or r["_field"] == "vibration")
          |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
          |> keep(columns: ["_time", "sn", "temperature", "vibration", "group_id"])
        '''
        
        result = self.query_api.query_data_frame(query, org=self.client.org)
        
        if isinstance(result, list):
            df = pd.concat(result) if result else pd.DataFrame()
        else:
            df = result
            
        if not df.empty:
            df['_time'] = pd.to_datetime(df['_time'])
            df.sort_values(by='_time', inplace=True)
            df.set_index('_time', inplace=True)
            
        return df

    def method_1_threshold(self, df, target_sn, temp_limit, vib_limit):
        """
        1. 阈值判断：针对指定 SN 判断最新数据是否超标
        """
        device_data = df[df['sn'] == target_sn]
        if device_data.empty:
            return []
            
        latest_row = device_data.iloc[-1]
        alarms = []
        
        if latest_row['temperature'] > temp_limit:
            alarms.append(f"【阈值报警】设备 {target_sn} 温度异常 ({latest_row['temperature']:.2f} > {temp_limit})")
        if latest_row['vibration'] > vib_limit:
            alarms.append(f"【阈值报警】设备 {target_sn} 振动异常 ({latest_row['vibration']:.2f} > {vib_limit})")
                
        return alarms

    def method_2_trend_and_3sigma(self, df, target_sn, target_field='vibration', window=12):
        """
        2. 时间线性比较：针对指定 SN 判断持续抬升且突破 3σ
        """
        device_data = df[df['sn'] == target_sn]
        if len(device_data) < window:
            return [] 

        recent_data = device_data.tail(window)[target_field].values
        
        # a. 线性趋势判断
        x = np.arange(len(recent_data))
        slope, intercept, r_value, p_value, std_err = linregress(x, recent_data)
        
        # b. 3σ 判断 (用前 N-1 个点计算基准，对比最新点)
        historical_data = recent_data[:-1] 
        current_value = recent_data[-1]
        
        mu = np.mean(historical_data)
        sigma = np.std(historical_data)
        
        alarms = []
        if slope > 0 and current_value > (mu + 3 * sigma):
            alarms.append(
                f"【趋势与3σ报警】设备 {target_sn} 的 {target_field} 持续抬升，"
                f"且最新值 {current_value:.2f} 突破 3σ 上限 ({mu + 3 * sigma:.2f})"
            )
            
        return alarms

    def method_3_group_comparison(self, df, target_sn, target_field='temperature', deviation_ratio=1.5):
        """
        3. 同组横向比较：判断指定 SN 是否严重偏离同组其他设备的均值
        """
        # 获取整组设备各自的最新数据点
        latest_group_data = df.groupby('sn').last()
        
        if len(latest_group_data) < 2 or target_sn not in latest_group_data.index:
            return [] 
            
        group_mean = latest_group_data[target_field].mean()
        group_std = latest_group_data[target_field].std()
        target_value = latest_group_data.loc[target_sn, target_field]
        
        alarms = []
        # 判断目标 SN 的值是否异常偏离均值
        if abs(target_value - group_mean) > (deviation_ratio * group_std):
            alarms.append(
                f"【横向对比报警】设备 {target_sn} 的 {target_field} ({target_value:.2f}) "
                f"严重偏离同组均值 ({group_mean:.2f})"
            )
                
        return alarms

    def diagnose_single_device(self, target_sn, group_id, measurement="pump_station_metrics"):
        """
        针对单台设备的综合诊断入口
        """
        # 为了支持同组对比，我们直接拉取该 SN 所在组的全部数据
        df = self.fetch_group_data(measurement=measurement, group_id=group_id, hours=24)
        
        if df.empty or target_sn not in df['sn'].values:
            return [f"未查询到设备 {target_sn} 的数据"]
            
        report = []
        
        # 1. 阈值检测
        report.extend(self.method_1_threshold(df, target_sn, temp_limit=85.0, vib_limit=15.0))
        
        # 2. 趋势与 3σ 检测
        report.extend(self.method_2_trend_and_3sigma(df, target_sn, 'vibration', window=12))
        report.extend(self.method_2_trend_and_3sigma(df, target_sn, 'temperature', window=12))
        
        # 3. 同组横向对比
        report.extend(self.method_3_group_comparison(df, target_sn, 'vibration'))
        report.extend(self.method_3_group_comparison(df, target_sn, 'temperature'))
        
        if not report:
            return [f"设备 {target_sn} 状态正常，未触发任何报警规则。"]
            
        return report

# 使用示例
# sys = EquipmentDiagnosisSystem(url="...", token="...", org="...", bucket="...")
# results = sys.diagnose_single_device(target_sn="PUMP-001", group_id="STATION-A")
# for r in results:
#     print(r)