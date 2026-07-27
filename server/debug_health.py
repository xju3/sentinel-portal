import asyncio
import os
from dotenv import load_dotenv
load_dotenv()

async def main():
    from pub.manager.database import db_manager, redis_manager
    import redis as redis_lib
    from uuid import UUID
    from pub.utils.redis_keys import REDIS_KEY_DIA_HEALTH_STATUS

    await db_manager.init(mysql_url=os.environ["MYSQL_URL"])

    redis_client = redis_lib.from_url(os.environ["REDIS_URL"], decode_responses=True)

    async with db_manager.SessionLocal() as session:
        from pub.services.dashboard.dashboard_health_service import DashboardHealthService

        devices = await DashboardHealthService._query_devices(session, UUID("b9515e9c-379a-4525-bfc0-0766bfcc5aa4"))
        print(f"_query_devices returned {len(devices)} devices")
        for did, dev in list(devices.items())[:3]:
            print(f"  key={did!r}  name={dev['device_name']}")

        print()
        # Simulate Redis hmget
        device_ids_list = list(devices.keys())
        redis_query_keys = [str(UUID(d)) for d in device_ids_list]
        print("Sample redis_query_keys:", redis_query_keys[:3])

        cached_levels = redis_client.hmget(REDIS_KEY_DIA_HEALTH_STATUS, *redis_query_keys)
        print("Sample cached_levels:", cached_levels[:5])

        fault_device_ids = set()
        for dev_id, level_str in zip(device_ids_list, cached_levels):
            if level_str is not None:
                score = int(level_str)
                if score > 0:
                    fault_device_ids.add(dev_id)
                    print(f"  FAULT: dev_id={dev_id}  level={score}")
            else:
                print(f"  MISS: dev_id={dev_id}")

        print(f"\nfault_device_ids: {fault_device_ids}")

        if fault_device_ids:
            fault_uuids = {UUID(d) for d in fault_device_ids}
            print(f"fault_uuids: {fault_uuids}")
            latest = await DashboardHealthService._query_latest_diagnosis(session, fault_uuids)
            print(f"latest_results keys: {list(latest.keys())}")

if __name__ == "__main__":
    asyncio.run(main())
