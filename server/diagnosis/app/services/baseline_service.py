import logging
import uuid
import statistics
from datetime import datetime
from typing import Optional

from sqlalchemy import select, update

from pub.manager.database import db_manager, influxdb_manager
from pub.models.device import DeviceBaseline, DeviceInst

logger = logging.getLogger(__name__)

class BaselineService:
    @staticmethod
    async def get_active_baseline(device_inst_id: str, metric_name: str = "max_rms_vel") -> float:
        """
        Fetch the currently active baseline for a device and metric.
        If no active baseline exists, returns 0.0 (Cold Start mode).
        """
        async with db_manager.SessionLocal() as session:
            stmt = select(DeviceBaseline).where(
                DeviceBaseline.device_inst_id == uuid.UUID(device_inst_id),
                DeviceBaseline.metric_name == metric_name,
                DeviceBaseline.effective_to.is_(None)
            ).order_by(DeviceBaseline.created_at.desc())
            
            result = await session.execute(stmt)
            baseline = result.scalars().first()
            
            if baseline:
                return baseline.baseline_value
            return 0.0

    @staticmethod
    async def calculate_and_roll_baseline(device_inst_id: str, metric_name: str = "max_rms_vel", days: int = 7) -> Optional[float]:
        """
        Query InfluxDB for the last N days of data, calculate the median,
        retire the old baseline, and create a new one.
        """
        client = influxdb_manager.get_client()
        if not client:
            logger.error("InfluxDB client not available for baseline calculation.")
            return None
            
        try:
            # Query InfluxDB for the historical data
            query = f'''
                from(bucket: "{influxdb_manager.bucket}")
                  |> range(start: -{days}d)
                  |> filter(fn: (r) => r["_measurement"] == "vibration_feature")
                  |> filter(fn: (r) => r["device_id"] == "{device_inst_id}")
                  |> filter(fn: (r) => r["_field"] == "{metric_name}")
                  |> filter(fn: (r) => r["_value"] > 0.1) // Filter out noise/downtime
            '''
            
            query_api = client.query_api()
            # Note: The influxdb-client-python async API is actually synchronous in many wrappers,
            # but we assume query_api().query() works or query_api.query_async is available.
            # Usually, influxdb client requires specific async initialization. 
            # If query_api doesn't have query_async, we might need asyncio.to_thread
            import asyncio
            tables = await asyncio.to_thread(query_api.query, query, org=influxdb_manager.org)
            
            values = []
            for table in tables:
                for record in table.records:
                    values.append(record.get_value())
                    
            if not values:
                logger.warning(f"No active data found for device {device_inst_id} in the last {days} days.")
                return None
                
            # Calculate the median
            median_value = statistics.median(values)
            
            # Persist to MySQL
            async with db_manager.SessionLocal() as session:
                async with session.begin():
                    # 1. Retire the old baseline
                    retire_stmt = update(DeviceBaseline).where(
                        DeviceBaseline.device_inst_id == uuid.UUID(device_inst_id),
                        DeviceBaseline.metric_name == metric_name,
                        DeviceBaseline.effective_to.is_(None)
                    ).values(effective_to=datetime.utcnow())
                    await session.execute(retire_stmt)
                    
                    # 2. Insert new baseline
                    new_baseline = DeviceBaseline(
                        device_inst_id=uuid.UUID(device_inst_id),
                        metric_name=metric_name,
                        baseline_value=median_value
                    )
                    session.add(new_baseline)
                    
            logger.info(f"Successfully rolled baseline for {device_inst_id} ({metric_name}): {median_value:.3f}")
            return median_value
            
        except Exception as e:
            logger.error(f"Failed to calculate baseline for {device_inst_id}: {str(e)}", exc_info=True)
            return None

    @staticmethod
    async def reset_baseline(device_inst_id: str, metric_name: str = "max_rms_vel") -> bool:
        """
        Manually retire the current baseline (e.g. after maintenance).
        The device will fall back to Cold Start mode (0.0) until the next rolling update.
        """
        try:
            async with db_manager.SessionLocal() as session:
                async with session.begin():
                    stmt = update(DeviceBaseline).where(
                        DeviceBaseline.device_inst_id == uuid.UUID(device_inst_id),
                        DeviceBaseline.metric_name == metric_name,
                        DeviceBaseline.effective_to.is_(None)
                    ).values(effective_to=datetime.utcnow())
                    await session.execute(stmt)
            logger.info(f"Successfully reset baseline for device {device_inst_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to reset baseline for {device_inst_id}: {str(e)}")
            return False
