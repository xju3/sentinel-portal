from typing import Any, Optional, List
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, ConfigDict

# 依赖于您的实际项目结构，如果 db_manager 中存在 get_session 则使用该方式注入
from pub.manager.database import db_manager
from pub.services import SimCardService
from app.utils.response import success

router = APIRouter(prefix="/sim-cards", tags=["SIM Cards"])

# ==========================================
# Pydantic Schemas (数据交互模型)
# ==========================================
class SimCardBase(BaseModel):
    ccid: str
    carrier: str
    data_plan: str
    status: int = 1
    activated_at: Optional[datetime] = None
    expires_at: datetime

class SimCardCreate(SimCardBase):
    pass

class SimCardUpdate(SimCardBase):
    # 更新时所有字段均可选
    pass

class SimCardOut(SimCardBase):
    id: UUID
    model_config = ConfigDict(from_attributes=True)

@router.get("/")
async def get_sim_cards_paged(
    current: int = Query(1, description="当前页码"),
    page_size: int = Query(20, description="每页数量"),
    keyword: Optional[str] = Query(None, description="搜索关键字(卡号/ICCID/运营商)"),
    status: Optional[int] = Query(None, description="状态筛选(1=正常, 0=停用)"),
    unbound_only: bool = Query(False, description="仅查询未绑定的 SIM 卡"),
    unactivated_only: bool = Query(False, description="仅查询未激活(activated_at为空)的 SIM 卡"),
    sort_by: Optional[str] = Query(None, description="排序字段"),
    sort_order: str = Query("ascend", description="排序方向"),
    session: AsyncSession = Depends(db_manager.get_session)
) -> Any:
    """获取 SIM 卡分页列表，用于管理界面的表格展示"""
    items, total = await SimCardService.get_paged(
        session, current, page_size, keyword, status, unbound_only, unactivated_only, sort_by, sort_order
    )
    
    # 将 SQLAlchemy 模型转换为 Pydantic 字典并自动处理 UUID/DateTime 到 String 的格式化
    list_data = [SimCardOut.model_validate(item).model_dump(mode='json') for item in items]
    return success({
        "list": list_data,
        "total": total,
        "current": current,
        "pageSize": page_size
    })

@router.post("/")
async def create_sim_card(
    data: SimCardCreate,
    session: AsyncSession = Depends(db_manager.get_session)
) -> Any:
    """创建新 SIM 卡记录"""
    # exclude_unset=True 能确保只传递实际有值的属性
    sim_card = await SimCardService.create(session, data.model_dump(exclude_unset=True))
    return success(SimCardOut.model_validate(sim_card).model_dump(mode='json'))

@router.put("/{obj_id}")
async def update_sim_card(
    obj_id: UUID,
    data: SimCardUpdate,
    session: AsyncSession = Depends(db_manager.get_session)
) -> Any:
    """更新指定的 SIM 卡信息"""
    sim_card = await SimCardService.get_by_id(session, obj_id)
    if not sim_card:
        raise HTTPException(status_code=404, detail="SIM Card not found")
    sim_card = await SimCardService.update(session, sim_card, data.model_dump(exclude_unset=True))
    return success(SimCardOut.model_validate(sim_card).model_dump(mode='json'))

@router.delete("/{obj_id}")
async def delete_sim_card(
    obj_id: UUID,
    session: AsyncSession = Depends(db_manager.get_session)
) -> Any:
    """删除指定的 SIM 卡"""
    sim_card = await SimCardService.get_by_id(session, obj_id)
    if not sim_card:
        raise HTTPException(status_code=404, detail="SIM Card not found")
    await SimCardService.delete(session, sim_card)
    return success()
