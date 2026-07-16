"""
Reusable sorting utility for SQLAlchemy-based list endpoints.

Frontend ProTable sends:
- sort_by  → field name (matching SQLAlchemy model attribute)
- sort_order → "ascend" or "descend"

This module maps the frontend request to safe SQLAlchemy order_by clauses.
"""

from typing import Any
from sqlalchemy import asc, desc, Select
from sqlalchemy.orm.attributes import QueryableAttribute


def apply_sorting(
    stmt: Select[Any],
    model_class: type,
    sort_by: str | None,
    sort_order: str = "ascend",
) -> Select[Any]:
    """
    Safely apply an ORDER BY clause to a SQLAlchemy SELECT statement.

    Only applies sorting when sort_by matches an actual column on model_class
    and is a valid QueryableAttribute. Otherwise returns the original statement unchanged.

    Args:
        stmt:        Existing SQLAlchemy select statement.
        model_class: The ORM model whose columns we may sort on.
        sort_by:     Frontend field name (e.g. "name", "created_at").
        sort_order:  "ascend" (default) or "descend".

    Returns:
        The select statement with order_by appended, or the original statement.
    """
    if not sort_by:
        return stmt

    col = getattr(model_class, sort_by, None)
    if col is None or not isinstance(col, QueryableAttribute):
        # Ignore unknown / non-column fields silently to avoid 500 errors
        return stmt

    if sort_order == "descend":
        return stmt.order_by(desc(col))
    return stmt.order_by(asc(col))