import asyncio
from pub.manager.database import db_manager
from pub.services.sensor.firmware_service import SensorFirmwareService

async def main():
    async with db_manager.get_session() as session:
        firmwares = await SensorFirmwareService.get_all(session, limit=1)
        print("Firmwares:", firmwares)

if __name__ == "__main__":
    asyncio.run(main())
