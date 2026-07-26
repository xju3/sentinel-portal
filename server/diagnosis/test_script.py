import sys
import json
import asyncio
from pydantic import ValidationError

# Set PYTHONPATH implicitly
sys.path.append("../pub/src")

from app.config import settings
from pub.manager.database import db_manager, redis_manager, influxdb_manager
from pub.models.report import DeviceDiagnosticReport
from app.preparation.ingestion import process_incoming_report

async def init_dbs():
    await db_manager.init(settings.mysql_url, settings.debug)
    redis_manager.init(settings.redis_url)
    influxdb_manager.init(settings.influx_url, settings.influx_token, settings.influx_org, settings.influx_bucket)

def verify_influxdb(ts_ms):
    query_api = influxdb_manager.get_client().query_api()
    query = f'''
    from(bucket:"{influxdb_manager.bucket}")
      |> range(start: 0)
      |> filter(fn: (r) => r._measurement == "vibration_feature")
      |> filter(fn: (r) => r._time == time(v: {ts_ms} * 1000000))
    '''
    result = query_api.query(org=influxdb_manager.org, query=query)
    print("\n[DB Verification] Querying InfluxDB for timestamp:", ts_ms)
    found = False
    for table in result:
        for record in table.records:
            print(f"  -> Found record in DB: Field={record.get_field()} Value={record.get_value()} Time={record.get_time()}")
            found = True
    if not found:
        print("  -> ❌ Data not found in InfluxDB!")
        sys.exit(1)
    else:
        print("  -> ✅ Data successfully verified in InfluxDB!")

async def verify_mysql(report_id):
    from pub.models.diagnosis import Diagnosis, DiagnosisItem
    from sqlalchemy import select
    
    async with db_manager.SessionLocal() as session:
        stmt = select(Diagnosis).where(Diagnosis.report_id == report_id)
        result = await session.execute(stmt)
        record = result.scalars().first()
        
        print("\n[DB Verification] Querying MySQL for report_id:", report_id)
        if not record:
            print("  -> ❌ Data not found in MySQL 'diagnosis' table!")
            sys.exit(1)
            
        print(f"  -> ✅ Found Diagnosis: id={record.id}, overall_level={record.overall_level}")
        
        stmt_item = select(DiagnosisItem).where(DiagnosisItem.diagnosis_id == record.id)
        items = (await session.execute(stmt_item)).scalars().all()
        for item in items:
            print(f"  -> ✅ Found DiagnosisItem: metric_id={item.metric_id}, level={item.level}, description='{item.description}', evidence={item.evidence}")

async def main_async():
    try:
        await init_dbs()
        
        with open("../docs/data.json", "r") as f:
            data = json.load(f)
        
        print("Validating payload...")
        report = DeviceDiagnosticReport(**data)
        
        print("Running ingestion process...")
        await process_incoming_report(report)
        
        # Verify
        verify_influxdb(report.ts_ms)
        await verify_mysql(report.report_id)
        
        print("\n✅ All tests passed successfully! Payload validated and ingested.")
    except Exception as e:
        print(f"\n❌ Error:\n{e}")
        sys.exit(1)
    finally:
        await db_manager.close()
        redis_manager.close()
        influxdb_manager.close()

if __name__ == "__main__":
    asyncio.run(main_async())
