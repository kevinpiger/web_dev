from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.utils.datetime import utcnow


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    """Timestamps are filled in Python as well as by the DDL default.

    The `server_default` keeps rows written outside the ORM correct; the Python-side
    `default`/`onupdate` means a freshly inserted object already carries the value, so
    serializing it right after commit never triggers an implicit lazy load (which raises
    MissingGreenlet under asyncio).
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        server_default=func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
