"""Reusable SQLAlchemy column type helpers."""

from __future__ import annotations

from enum import Enum as PyEnum
from typing import Any

from sqlalchemy import Enum as SAEnum


def enum_column(enum_cls: type[PyEnum], **kwargs: Any) -> SAEnum:
    """Build a portable ``ENUM`` column that persists the member *values*.

    ``native_enum=False`` keeps the schema portable (VARCHAR + CHECK) so the
    same models run on MySQL in production and SQLite in tests, while still
    validating the allowed values.
    """
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=32,
        validate_strings=True,
        values_callable=lambda enum: [member.value for member in enum],
        **kwargs,
    )
