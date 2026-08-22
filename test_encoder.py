from fastapi.encoders import jsonable_encoder
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import declarative_base, relationship
import asyncio
from pub.manager.database import db_manager
from pub.models.sensor import SensorFirmware, SensorType
from sqlalchemy import select

async def main():
    async with db_manager.get_session() as session:
        # fetch without joinedload
        stmt = select(SensorFirmware).limit(1)
        fw = (await session.execute(stmt)).scalar_one_or_none()
        if fw:
            print("Encoding...")
            try:
                res = jsonable_encoder(fw)
                print("Success:", res.keys())
            except Exception as e:
                print("Failed:", type(e), e)

if __name__ == "__main__":
    asyncio.run(main())
