import asyncio
from pub.manager.database import db_manager
from pub.services.dashboard.dashboard_health_service import DashboardHealthService

async def main():
    await db_manager.init()
    async with db_manager.SessionLocal() as session:
        res = await DashboardHealthService.get_health_dashboard(session, 1)
        import json
        print(json.dumps(res, indent=2, default=str))

if __name__ == "__main__":
    asyncio.run(main())
