"""
Common API response contract
"""

from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel

DataT = TypeVar("DataT")


class ApiResponse(BaseModel):
    """Unified API response format

    All API endpoints return responses in this format.
    Frontend should check the `code` field to determine success/failure.

    - code=0: success
    - code=401: unauthorized (frontend should redirect to login)
    - Other codes: various errors
    """
    code: int = 0
    message: str = ""
    data: Any = None
