"""
API response helper functions
"""

from typing import Any, Optional

from fastapi.encoders import jsonable_encoder

from pub.contract.common import ApiResponse


def success(data: Any = None, message: str = "ok") -> ApiResponse:
    """Return a successful API response

    Uses jsonable_encoder to pre-process the data so that SQLAlchemy models
    and other non-serializable types are converted to JSON-compatible dicts
    before being wrapped in ApiResponse. This avoids PydanticSerializationError
    in Pydantic v2.13+ when model_dump(mode='json') encounters unknown types.
    """
    return ApiResponse(code=0, message=message, data=jsonable_encoder(data))


def error(code: int, message: str = "", data: Any = None) -> ApiResponse:
    """Return an error API response"""
    return ApiResponse(code=code, message=message, data=data)
