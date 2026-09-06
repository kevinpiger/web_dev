"""Typed JSONB contract for result_info.workbench and its public response.

Result versions, render versions and verification rounds are separate sequences.
Artifact storage keys are internal; public responses expose authorized endpoints.
"""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.execution import ExecutionOut
from app.schemas.parse_item import ParseItemOut
from app.schemas.result import ResultOut

MatchValue = Literal["TRUE", "PARTIAL", "FALSE"]
ImageMediaType = Literal["image/png", "image/jpeg", "image/webp"]


class StoredArtifact(BaseModel):
    id: uuid.UUID
    storage_key: str = Field(min_length=1)
    media_type: ImageMediaType


class RenderVersion(BaseModel):
    id: uuid.UUID
    label: str = Field(min_length=1)
    artifact_id: uuid.UUID
    note: str | None = None
    # Unknown for image-only imports. Do not guess from v01/v02 or array position.
    result_id: uuid.UUID | None = None


class VerificationRound(BaseModel):
    round_no: int = Field(ge=1)
    match: MatchValue
    checked_at: datetime | None = None
    # Original report timestamps have no timezone; preserve without inventing UTC.
    checked_at_display: str | None = None
    diff_count: int | None = Field(default=None, ge=0)
    diffs: list[dict] | None = None
    input_result_id: uuid.UUID | None = None


class Verification(BaseModel):
    status: Literal["NOT_RUN", "RUNNING", "COMPLETED", "FAILED"] = "NOT_RUN"
    match: MatchValue | None = None
    rounds: list[VerificationRound] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent_summary(self):
        numbers = [r.round_no for r in self.rounds]
        if numbers != sorted(set(numbers)):
            raise ValueError("verification rounds must be ordered and unique")
        if self.status != "COMPLETED" and self.match is not None:
            raise ValueError("only completed verification may carry a final match")
        if self.status == "COMPLETED" and self.match is None:
            raise ValueError("completed verification requires a final match")
        return self


class Metric(BaseModel):
    label: str
    value: str | int | float | None


class MetricTable(BaseModel):
    columns: list[str] = Field(default_factory=list)
    rows: list[list[str | int | float | None]] = Field(default_factory=list)

    @model_validator(mode="after")
    def rectangular(self):
        if any(len(row) != len(self.columns) for row in self.rows):
            raise ValueError("metric row length must match columns")
        return self


class Conversion(BaseModel):
    kind: Literal["TESTBENCH", "REGISTER_DEFINITION"]
    language: Literal["VERILOG"] = "VERILOG"
    code: str
    metrics: list[Metric] = Field(default_factory=list)
    table: MetricTable = Field(default_factory=MetricTable)
    # null means warning details were not supplied, not zero warnings.
    warnings: list[str] | None = None


class WorkbenchData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    # Digest of result_info.content (UTF-8). Prevent stale derived data reuse.
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    artifacts: list[StoredArtifact] = Field(default_factory=list)
    source_artifact_id: uuid.UUID | None = None
    render_versions: list[RenderVersion] = Field(default_factory=list)
    verification: Verification = Field(default_factory=Verification)
    conversion: Conversion | None = None

    @model_validator(mode="after")
    def references_exist(self):
        artifact_ids = [a.id for a in self.artifacts]
        if len(set(artifact_ids)) != len(artifact_ids):
            raise ValueError("duplicate artifact id")
        if self.source_artifact_id and self.source_artifact_id not in artifact_ids:
            raise ValueError("source artifact is missing")
        if any(v.artifact_id not in artifact_ids for v in self.render_versions):
            raise ValueError("render artifact is missing")
        ids = [v.id for v in self.render_versions]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate render version id")
        return self


class ArtifactOut(BaseModel):
    id: uuid.UUID
    media_type: ImageMediaType
    content_url: str


class WorkbenchSource(BaseModel):
    asset_id: uuid.UUID
    file_name: str
    page_no: int
    asset_content_url: str
    preview_artifact: ArtifactOut | None = None


class WorkbenchOut(BaseModel):
    parse_item: ParseItemOut
    source: WorkbenchSource
    execution: ExecutionOut | None = None
    selected_result: ResultOut | None = None
    results: list[ResultOut] = Field(default_factory=list)
    data_status: Literal["NO_EXECUTION", "NO_RESULT", "LEGACY", "AVAILABLE", "STALE", "INVALID"]
    artifacts: list[ArtifactOut] = Field(default_factory=list)
    render_versions: list[RenderVersion] = Field(default_factory=list)
    verification: Verification = Field(default_factory=Verification)
    conversion: Conversion | None = None
