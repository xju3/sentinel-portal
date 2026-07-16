"""
Sensor service - business logic for sensor operations
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Optional, Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.client.query_api import QueryApi

from pub.manager.database import influxdb_manager, db_manager
from fastapi import BackgroundTasks
from pub.models.sensor import SensorType, Sensor, SensorBatch, SensorThreshold, SensorMonitoring, SimCard
from pub.models.device import DeviceInst, DeviceSpec, DeviceCategory, ProcessDeviceItem, ProcessDevice
from pub.models.customer import Tenant, Area, HealthCheckFreq, IsoStandard, Region
from pub.exceptions.domain_exception import DomainException
from pub.utils.sorting import apply_sorting
logger = logging.getLogger(__name__)

class SensorService:
    """Service for sensor operations"""

    @staticmethod
    def get_latest_reading(sensor_id: int) -> Optional[dict]:
        """
        Get the latest reading for a sensor
        
        Args:
            sensor_id: Sensor ID
            
        Returns:
            Latest reading or None
        """
        try:
            client = influxdb_manager.get_client()
            query_api = client.query_api(query_type="pandas")

            query = f'''
                from(bucket:"{influxdb_manager.bucket}")
                |> range(start: -1000d)
                |> filter(fn: (r) => r._measurement == "sensor_reading")
                |> filter(fn: (r) => r.sensor_id == "{sensor_id}")
                |> last()
            '''

            result = query_api.query(org=influxdb_manager.org, query=query)

            for table in result:
                for record in table.records:
                    return {
                        "timestamp": record.get_time(),
                        "value": record.get_value(),
                        "unit": record.values.get("unit"),
                    }

            return None
        except Exception as e:
            logger.error(f"Failed to get latest reading: {e}")
            return None

    @staticmethod
    async def get_sensor_history(session: AsyncSession, sn: str, time_range: str, window: Optional[str] = None) -> dict:
        """动态智能聚合读取传感器时序历史数据，保留网络断连造成的空窗期"""
        ranges = {'1w': 7, '2w': 14, '1m': 30, '2m': 60, '3m': 90}
        days = ranges.get(time_range, 7)
        total_minutes = days * 24 * 60

        from pub.services.customer.health_check_freq_service import HealthCheckFreqService
        freq = await HealthCheckFreqService.get_health_check_by_sensor_sn(session, sn)
        patrol_m = freq.patrol if freq else 60
        
        # 获取传感器的安装方向以供前端动态推断 XYZ 轴的真实物理含义
        direction_stmt = select(SensorMonitoring.direction).join(
            Sensor, Sensor.id == SensorMonitoring.sensor_id
        ).where(Sensor.sn == sn)
        direction_result = await session.execute(direction_stmt)
        direction = direction_result.scalar_one_or_none()

        # 计算实际的聚合粒度
        if window and window != 'auto':
            win_m = 60
            if window.endswith('h'):
                win_m = int(window[:-1]) * 60
            elif window.endswith('d'):
                win_m = int(window[:-1]) * 1440
            target_window_m = max(patrol_m, win_m) # 绝不能低于真实的采样频率
        else:
            # 智能适配最适宜的图表颗粒度：保证前端数据点数在合理的150个以内
            target_window_m = max(patrol_m, total_minutes // 150)

        # Flux 时间单位格式化
        if target_window_m >= 1440 and target_window_m % 1440 == 0:
            window_str = f"{target_window_m // 1440}d"
        elif target_window_m >= 60 and target_window_m % 60 == 0:
            window_str = f"{target_window_m // 60}h"
        else:
            window_str = f"{target_window_m}m"

        try:
            client = influxdb_manager.get_client()
            query_api = client.query_api()

            # Flux 查询: 提取基础数据后，不仅查 max，针对 rms_m 并发查询 min, first, last 凑齐 Candlestick 所需的 4 要素
            query = f'''
                data = from(bucket:"{influxdb_manager.bucket}")
                    |> range(start: -{days}d)
                    |> filter(fn: (r) => r.sn == "{sn}")
                    |> filter(fn: (r) => r._field == "temperature" or r._field == "rms_x" or r._field == "rms_y" or r._field == "rms_z" or r._field == "rms_m")
                
                data |> aggregateWindow(every: {window_str}, fn: max, createEmpty: true) |> yield(name: "max")
                data |> filter(fn: (r) => r._field == "rms_m" or r._field == "temperature") |> aggregateWindow(every: {window_str}, fn: min, createEmpty: true) |> yield(name: "min")
                data |> filter(fn: (r) => r._field == "rms_m" or r._field == "temperature") |> aggregateWindow(every: {window_str}, fn: first, createEmpty: true) |> yield(name: "first")
                data |> filter(fn: (r) => r._field == "rms_m" or r._field == "temperature") |> aggregateWindow(every: {window_str}, fn: last, createEmpty: true) |> yield(name: "last")
            '''

            result = await asyncio.to_thread(query_api.query, org=influxdb_manager.org, query=query)

            # 拼装数据对齐字典
            data_map = {}
            for table in result:
                yield_name = table.records[0].values.get("result") if table.records else None
                for record in table.records:
                    t = record.get_time().isoformat()
                    f = record.get_field()
                    v = record.get_value()
                    if t not in data_map:
                        data_map[t] = {
                            "temperature": None, "rms_x": None, "rms_y": None, "rms_z": None, "rms_m": None,
                            "rms_m_min": None, "rms_m_first": None, "rms_m_last": None,
                            "temp_min": None, "temp_first": None, "temp_last": None
                        }
                        
                    if yield_name == "max" and f in data_map[t]:
                        data_map[t][f] = v
                    elif yield_name == "min":
                        if f == "rms_m": data_map[t]["rms_m_min"] = v
                        elif f == "temperature": data_map[t]["temp_min"] = v
                    elif yield_name == "first":
                        if f == "rms_m": data_map[t]["rms_m_first"] = v
                        elif f == "temperature": data_map[t]["temp_first"] = v
                    elif yield_name == "last":
                        if f == "rms_m": data_map[t]["rms_m_last"] = v
                        elif f == "temperature": data_map[t]["temp_last"] = v

            sorted_times = sorted(data_map.keys())
            
            return {
                "meta": {
                    "patrol": patrol_m,
                    "window": window_str,
                    "points": len(sorted_times),
                    "direction": direction
                },
                "timestamps": sorted_times,
                "series": {
                    "temperature": [data_map[t]["temperature"] for t in sorted_times],
                    "temp_min": [data_map[t].get("temp_min") for t in sorted_times],
                    "temp_first": [data_map[t].get("temp_first") for t in sorted_times],
                    "temp_last": [data_map[t].get("temp_last") for t in sorted_times],
                    "rms_x": [data_map[t]["rms_x"] for t in sorted_times],
                    "rms_y": [data_map[t]["rms_y"] for t in sorted_times],
                    "rms_z": [data_map[t]["rms_z"] for t in sorted_times],
                    "rms_m": [data_map[t]["rms_m"] for t in sorted_times],
                    "rms_m_min": [data_map[t].get("rms_m_min") for t in sorted_times],
                    "rms_m_first": [data_map[t].get("rms_m_first") for t in sorted_times],
                    "rms_m_last": [data_map[t].get("rms_m_last") for t in sorted_times],
                }
            }
        except Exception as e:
            logger.error(f"Failed to get sensor history for SN {sn}: {e}")
            raise DomainException(code=500, message=f"时序数据库查询失败: {str(e)}")
