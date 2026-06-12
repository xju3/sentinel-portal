"""
SQLAlchemy models for MySQL database
"""

from sqlalchemy.orm import declarative_base

Base = declarative_base()


def import_all_models() -> None:
    """Register every SQLAlchemy model before metadata create_all runs."""
    from pub.models import customer as customer  # noqa: F401
    from pub.models import device as device  # noqa: F401
    from pub.models import diagnosis as diagnosis  # noqa: F401
    from pub.models import sensor as sensor  # noqa: F401
