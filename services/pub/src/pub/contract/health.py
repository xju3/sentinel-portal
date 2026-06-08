"""
Health check API contracts
"""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Health check response model"""

    status: str
    message: str
    services: dict
