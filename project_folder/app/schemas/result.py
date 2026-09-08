import uuid
from datetime import datetime

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ResultOut(BaseModel):
    id: uuid.UUID
    execution_id: uuid.UUID
    round_no: int
    status: str
    result_info: dict
    created_at: datetime

    model_config = {"from_attributes": True}


class ResultAppend(BaseModel):
    """A user edit of 最終解析程式.

    Never overwrites: each save appends the next `round_no` for the execution, so the
    version history (v01 / v02 / 最終) stays intact and auditable.
    """

    # New clients send both IDs to prevent stale edits crossing executions/results.
    execution_id: uuid.UUID | None = None
    base_result_id: uuid.UUID | None = None
    content: str = Field(min_length=1)
    content_type: str | None = None
    type: str | None = None
    note: str | None = None


class ExecutionResultCreate(BaseModel):
    """Raw result JSON for the token-free test endpoint."""

    model_config = ConfigDict(extra="forbid")

    result_info: dict[str, Any]
