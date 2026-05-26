import logging
import inspect
from functools import wraps
from uuid import UUID
from typing import Optional

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
