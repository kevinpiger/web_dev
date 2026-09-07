import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from app.schemas.workbench import Conversion, RenderVersion, Verification


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AttemptCreate(StrictModel):
    attempt_id: uuid.UUID


class AttemptState(BaseModel):
    execution_id: uuid.UUID
    attempt_id: uuid.UUID | None
    attempt_no: int | None
    execution_status: str
    attempt_status: str | None
    lease_expires_at: datetime | None
    token_expires_at: datetime | None
    retry_allowed: bool
    stop: bool
    reason: str | None


class WorkerState(AttemptState):
    latest_result_id: uuid.UUID | None


class AttemptGrant(AttemptState):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    heartbeat_interval_seconds: int


class AgentWorkbench(StrictModel):
    artifact_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    source_artifact_id: uuid.UUID | None = None
    render_versions: list[RenderVersion] = Field(default_factory=list, max_length=100)
    verification: Verification = Field(default_factory=Verification)
    conversion: Conversion | None = None


class ResultSubmission(StrictModel):
    request_id: uuid.UUID
    result_id: uuid.UUID
    type: str = Field(min_length=1, max_length=100)
    content_type: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=2_000_000)
    note: str | None = Field(default=None, max_length=10000)
    workbench: AgentWorkbench = Field(default_factory=AgentWorkbench)


class FailureSubmission(StrictModel):
    request_id: uuid.UUID
    status: Literal["FAILED", "TIMEOUT"] = "FAILED"
    error_code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=4000)
    retryable: bool = False


class ResultReceipt(BaseModel):
    request_id: uuid.UUID
    result_id: uuid.UUID
    round_no: int
    execution_status: str
    attempt_status: str


class FailureReceipt(BaseModel):
    request_id: uuid.UUID
    execution_status: str
    attempt_status: str
    retry_allowed: bool


class ArtifactReceipt(BaseModel):
    artifact_id: uuid.UUID
    result_id: uuid.UUID
    media_type: str
    size: int
    sha256: str


class SourceInfo(BaseModel):
    asset_id: uuid.UUID
    file_name: str
    content_url: str
    page_no: int
    roi: dict[str, float]


class ComponentInfo(BaseModel):
    id: str | None
    version: str | None


class AgentContext(BaseModel):
    task_id: uuid.UUID
    parse_id: uuid.UUID
    execution_id: uuid.UUID
    attempt_id: uuid.UUID
    name: str | None
    source: SourceInfo
    flow: ComponentInfo
    model: ComponentInfo
    lease_expires_at: datetime
    token_expires_at: datetime
