import uuid
from datetime import datetime

from pydantic import BaseModel


class ExecutionOut(BaseModel):
    id: uuid.UUID
    parse_id: uuid.UUID
    status: str
    retry_count: int
    max_retry_count: int
    flow_id: str | None
    flow_version: str | None
    model_id: str | None
    model_version: str | None
    input_data: dict
    queued_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    error_code: str | None
    error_message: str | None
    review_status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DispatchResult(BaseModel):
    """Result of 送出任務 — executions created and handed to the outbox (not yet published)."""

    task_id: uuid.UUID
    task_status: str
    dispatched_count: int
    executions: list[ExecutionOut]


class CancelResult(BaseModel):
    task_id: uuid.UUID | None = None
    task_status: str | None = None
    cancelled_executions: int
