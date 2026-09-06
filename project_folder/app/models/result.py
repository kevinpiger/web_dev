import uuid

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Result(TimestampMixin, Base):
    """Immutable content snapshot. result_info.workbench follows WorkbenchData;
    render versions and verification rounds do not determine round_no.
    """

    __tablename__ = "result"
    __table_args__ = (
        UniqueConstraint("execution_id", "round_no", name="result_execution_round_unique"),
        {"schema": "core"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("core.execution.id", ondelete="CASCADE"), nullable=False
    )
    round_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    result_info: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
