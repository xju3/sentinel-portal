"""
Domain exception definitions

All business logic exceptions should inherit from DomainException.
The global exception handler in main.py catches DomainException and returns
a unified ApiResponse format to the frontend.
"""


class DomainException(Exception):
    """Base exception for all domain/business logic errors.

    Attributes:
        code: Business error code (e.g. 400, 404, 409, etc.)
        message: Human-readable error description
    """

    def __init__(self, code: int, message: str = ""):
        self.code = code
        self.message = message
        super().__init__(self.message)
