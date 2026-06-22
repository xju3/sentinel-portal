"""
Global exception handlers for FastAPI application.

All exception handlers return HTTP 200 status code with the actual error
code embedded in the response body. This ensures axios treats all responses
as successful HTTP requests, allowing the frontend interceptor to handle
business logic errors (code !== 0) uniformly.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from pub.contract.common import ApiResponse
from pub.exceptions.domain_exception import DomainException

logger = logging.getLogger(__name__)


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions and return unified ApiResponse format"""
    logger.warning(
        "HTTP %d on %s %s: %s",
        exc.status_code,
        request.method,
        request.url.path,
        exc.detail,
    )
    return JSONResponse(
        status_code=200,
        content=jsonable_encoder(
            ApiResponse(code=exc.status_code, message=str(exc.detail), data=None)
        ),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors"""
    errors = exc.errors()
    logger.warning(
        "Validation error on %s %s: %s",
        request.method,
        request.url.path,
        errors,
    )
    return JSONResponse(
        status_code=200,
        content=jsonable_encoder(
            ApiResponse(code=422, message=str(errors), data=None)
        ),
    )


async def domain_exception_handler(request: Request, exc: DomainException):
    """Handle domain/business logic exceptions and return unified ApiResponse format"""
    logger.warning(
        "Domain error on %s %s: code=%d, message=%s",
        request.method,
        request.url.path,
        exc.code,
        exc.message,
    )
    return JSONResponse(
        status_code=200,
        content=jsonable_encoder(
            ApiResponse(code=exc.code, message=exc.message, data=None)
        ),
    )


async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions"""
    logger.error(
        "Unhandled error on %s %s: %s",
        request.method,
        request.url.path,
        exc,
        exc_info=True,
    )
    return JSONResponse(
        status_code=200,
        content=jsonable_encoder(
            ApiResponse(code=500, message="Internal server error", data=None)
        ),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all global exception handlers on the given FastAPI application."""
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(DomainException, domain_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
