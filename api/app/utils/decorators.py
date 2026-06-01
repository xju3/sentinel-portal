import logging
import inspect
from functools import wraps
from uuid import UUID
from typing import Optional, Type

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.dashboard_service import DashboardService

logger = logging.getLogger(__name__)


def rebuild_dashboard_cache():
    """
    用于 FastAPI 路由的装饰器：在执行 CUD 操作后，清除 Dashboard 拓扑结构缓存。
    
    本装饰器专为 Route 层设计，通过以下方式获取 tenant_id：
    1. kwargs 中的 `current_account` 依赖注入（标准方式）
    2. kwargs 中的 `tenant_id` 参数
    3. args 中的 SQLAlchemy 模型对象（如 db_obj）的 tenant_id 属性
    
    缓存重建由下次访问时的缓存穿透机制自动触发，避免在当前请求中执行耗时操作。
    
    使用方式：
        @router.post("/some-resource")
        @rebuild_dashboard_cache()
        async def create_something(
            ...,
            current_account: AccountModel = Depends(get_current_account),
        ):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            _invalidate_cache(args, kwargs, func.__name__)
            return result

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            _invalidate_cache(args, kwargs, func.__name__)
            return result

        return async_wrapper if inspect.iscoroutinefunction(func) else sync_wrapper

    return decorator


def _invalidate_cache(args: tuple, kwargs: dict, func_name: str) -> None:
    """从 args/kwargs 中提取 tenant_id 并清除缓存。"""
    tenant_id: Optional[UUID] = None

    # 1. 优先从 current_account 获取（Route 层标准方式）
    current_account = kwargs.get("current_account")
    if current_account is not None and hasattr(current_account, "tenant_id"):
        tenant_id = current_account.tenant_id

    # 2. 回退：从 kwargs 中的 tenant_id 参数获取
    if tenant_id is None and "tenant_id" in kwargs:
        tenant_id = kwargs["tenant_id"]

    # 3. 回退：从 args 中的 SQLAlchemy 模型对象获取
    if tenant_id is None:
        for arg in args:
            if hasattr(arg, "tenant_id") and arg.tenant_id is not None:
                tenant_id = arg.tenant_id
                break

    if tenant_id is not None:
        try:
            if isinstance(tenant_id, str):
                tenant_id = UUID(tenant_id)
            DashboardService.invalidate_device_stats_cache(tenant_id)
        except Exception as e:
            logger.error(f"Failed to invalidate dashboard cache in {func_name}: {e}")
    else:
        logger.warning(
            f"rebuild_dashboard_cache 装饰器在 {func_name} 上未找到 tenant_id，跳过缓存重建。"
        )


# ==========================================
# monitor_config_change
# ==========================================

def monitor_config_change(model_class: Type, obj_id_param: str, new_data_param: str):
    """装饰器：监控影响 /sensors/config/{sn} 的数据变更。

    用于 FastAPI 路由的 CUD 端点。在操作执行前抓取旧记录，执行后对比
    核心字段是否变化，变化时反向追溯到受影响的 sensor.sn，记录日志并
    为每个受影响的传感器创建 SensorTask 配置更新任务。

    参数:
        model_class:    SQLAlchemy 模型类（如 DeviceCategory, IsoStandard）
        obj_id_param:   kwargs 中记录 ID 的参数名（如 "obj_id", "area_id"）
        new_data_param: kwargs 中新数据的参数名（如 "item", "area"）

    使用方式:
        @router.put("/device-categories/{obj_id}")
        @monitor_config_change(DeviceCategory, "obj_id", "item")
        @rebuild_dashboard_cache()
        async def update_device_category(...):
            ...
    """
    from app.services.config_service import handle_config_change

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            session: Optional[AsyncSession] = kwargs.get("session")
            obj_id_val = kwargs.get(obj_id_param)
            new_data = kwargs.get(new_data_param)

            # 从 obj_id_param 提取记录 ID，优先从 current_account.tenant_id 获取
            obj_id: Optional[UUID] = None
            if obj_id_val is not None and hasattr(obj_id_val, "tenant_id"):
                obj_id = obj_id_val.tenant_id
            elif obj_id_val is not None and hasattr(obj_id_val, "id"):
                obj_id = obj_id_val.id
            else:
                obj_id = obj_id_val

            logger.info(
                f"[ConfigChange] 装饰器触发: model={model_class.__name__}, "
                f"session={session is not None}, obj_id={obj_id}, new_data={new_data is not None}"
            )

            # 在 CUD 前抓取旧记录，并立即从 session 剥离防止 commit 后值被刷新
            old_record = None
            if session is not None and obj_id is not None:
                try:
                    stmt = select(model_class).where(model_class.id == obj_id)
                    result = await session.execute(stmt)
                    old_record = result.scalar_one_or_none()
                    if old_record is not None:
                        session.expunge(old_record)
                    logger.debug(f"[ConfigChange] CUD 前旧记录抓取完成: {old_record is not None}")
                except Exception as exc:
                    logger.warning(f"[ConfigChange] CUD 前旧记录抓取异常: {exc}")
                    old_record = None

            # 执行 CUD 操作
            result = await func(*args, **kwargs)

            # 检测并处理配置变更
            if session is not None and obj_id is not None and new_data is not None:
                try:
                    await handle_config_change(session, model_class, obj_id, new_data, old_record)
                except Exception as e:
                    logger.error(
                        f"[ConfigChange] 检测 {model_class.__name__}(id={obj_id}) 变更时出错: {e}"
                    )
            else:
                logger.warning(
                    f"[ConfigChange] 跳过检测: session={session is not None}, "
                    f"obj_id={obj_id is not None}, new_data={new_data is not None}"
                )

            return result

        return async_wrapper

    return decorator
