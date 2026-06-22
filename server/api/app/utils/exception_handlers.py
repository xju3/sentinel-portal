"""
Re-export exception handlers from the shared pub package.

This module exists for backward compatibility so that existing
imports like `from app.utils.exception_handlers import ...` still work.
"""

from pub.exceptions.exception_handlers import (  # noqa: F401
    http_exception_handler,
    validation_exception_handler,
    domain_exception_handler,
    general_exception_handler,
    register_exception_handlers,
)
