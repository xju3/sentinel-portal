import logging
import inspect
import asyncio
from functools import wraps
from uuid import UUID
from typing import Optional, Type

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.dashboard_service import DashboardService

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


# ==========================================
# monitor_config_change
# ==========================================

def monitor_config_change(model_class: Type, obj_id_param: str, new_data_param: str):
    """Decorator: monitor data changes that affect /sensors/config/{sn}.

    Fetches the old record before the CUD operation, then launches a
    background task (asyncio.create_task) to compare old/new values,
    trace affected sensors, create SensorTask records, and publish
    MQTT notifications — all without blocking the HTTP response.

    Args:
        model_class:    SQLAlchemy model class (e.g. DeviceCategory, IsoStandard)
        obj_id_param:   kwargs key for the record ID (e.g. "obj_id", "area_id")
        new_data_param: kwargs key for the new data (e.g. "item", "area")
    """
    from app.services.config_service import bg_handle_config_change

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            session: Optional[AsyncSession] = kwargs.get("session")
            obj_id_val = kwargs.get(obj_id_param)
            new_data = kwargs.get(new_data_param)

            # Extract record ID from kwargs
            obj_id: Optional[UUID] = None
            if obj_id_val is not None and hasattr(obj_id_val, "tenant_id"):
                obj_id = obj_id_val.tenant_id
            elif obj_id_val is not None and hasattr(obj_id_val, "id"):
                obj_id = obj_id_val.id
            else:
                obj_id = obj_id_val

            logger.info(
                f"[ConfigChange] decorator triggered: model={model_class.__name__}, "
                f"session={session is not None}, obj_id={obj_id}, new_data={new_data is not None}"
            )

            # Snapshot old record values BEFORE the CUD operation
            old_values: Optional[dict] = None
            if session is not None and obj_id is not None:
                try:
                    stmt = select(model_class).where(model_class.id == obj_id)
                    result = await session.execute(stmt)
                    old_record = result.scalar_one_or_none()
                    if old_record is not None:
                        # Convert to plain dict — completely detached from session
                        cols = [c.key for c in model_class.__table__.columns]
                        old_values = {c: getattr(old_record, c) for c in cols}
                    logger.debug(f"[ConfigChange] old record snapshot: {old_values is not None}")
                except Exception as exc:
                    logger.warning(f"[ConfigChange] old record snapshot failed: {exc}")

            # Execute CUD operation (original route handler)
            result = await func(*args, **kwargs)

            # Launch background task — do NOT await, return response immediately
            if obj_id is not None and new_data is not None and old_values is not None:
                try:
                    asyncio.create_task(
                        bg_handle_config_change(model_class, obj_id, new_data, old_values)
                    )
                    logger.debug(f"[ConfigChange] background task launched for {model_class.__name__}(id={obj_id})")
                except Exception as e:
                    logger.error(
                        f"[ConfigChange] failed to launch background task for "
                        f"{model_class.__name__}(id={obj_id}): {e}"
                    )
            else:
                logger.debug(
                    f"[ConfigChange] skipped: obj_id={obj_id is not None}, "
                    f"new_data={new_data is not None}, old_values={old_values is not None}"
                )

            return result

        return async_wrapper

    return decorator