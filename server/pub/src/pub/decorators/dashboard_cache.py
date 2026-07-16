import logging
import inspect
from functools import wraps
from uuid import UUID
from typing import Optional

from pub.services import DashboardService

logger = logging.getLogger(__name__)

def rebuild_dashboard_cache():
    """
    For FastAPI routes: invalidate the dashboard topology cache after CUD operations.
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
    tenant_id: Optional[UUID] = None

    current_account = kwargs.get("current_account")
    if current_account is not None and hasattr(current_account, "tenant_id"):
        tenant_id = current_account.tenant_id

    if tenant_id is None and "tenant_id" in kwargs:
        tenant_id = kwargs["tenant_id"]

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
            f"rebuild_dashboard_cache decorator could not find tenant_id in {func_name}"
        )
