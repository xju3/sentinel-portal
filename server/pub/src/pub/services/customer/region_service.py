"""
Customer service - business logic for customer operations
"""

from uuid import UUID
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, or_

from pub.models.customer import (
    Region,
    Tenant,
    TenantSensor,
    Supplier,
    Contact,
    Account,
    Area,
    Location,
    HealthCheckFreq,
    IsoStandard,
)
from pub.exceptions.domain_exception import DomainException
from pub.utils.sorting import apply_sorting

from pub.models.sensor import SensorMonitoring, Sensor
from pub.models.device import DeviceCategory, DeviceSpec, DeviceInst

class RegionService:
    @staticmethod
    async def get_provinces(session: AsyncSession) -> List[Region]:
        stmt = select(Region).where(Region.level == 1, Region.available == True)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_children(session: AsyncSession, parent_id: str) -> List[Region]:
        stmt = select(Region).where(Region.parent_id == parent_id, Region.available == True)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_region_tree_2level(session: AsyncSession) -> List[dict]:
        stmt = select(Region).where(Region.level <= 2, Region.available == True)
        result = await session.execute(stmt)
        regions = result.scalars().all()
        
        region_dict = {}
        for r in regions:
            region_dict[r.id] = {"value": r.id, "label": r.name, "level": r.level, "parent_id": r.parent_id}
            if r.level == 1:
                region_dict[r.id]["children"] = []
                
        tree = []
        for r in regions:
            node = region_dict.get(r.id)
            if not node: continue
            if r.level == 1:
                tree.append(node)
            elif r.level == 2 and r.parent_id in region_dict:
                region_dict[r.parent_id]["children"].append(node)
                
        return tree
