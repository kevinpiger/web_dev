"""Drawer/verify contract definitions; not yet wired into the v2 result APIs.

Step IDs remain stable between snapshots. Images reference the result artifact
registry, whose storage keys must never appear in public outputs.
"""
import uuid
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DrawerChange(StrictModel):
    target: str = Field(min_length=1)
    description: str = Field(min_length=1)
    suggestion_id: uuid.UUID | None = None


class DrawerOutput(StrictModel):
    type: Literal["TIMING", "REGISTER"]
    content_type: Literal["WAVEDROM"] = "WAVEDROM"
    content: dict
    render_artifact_id: uuid.UUID
    summary: str = Field(min_length=1)
    changes: list[DrawerChange] = Field(default_factory=list)

    @model_validator(mode="after")
    def content_matches_type(self):
        key = "signal" if self.type == "TIMING" else "reg"
        if not isinstance(self.content.get(key), list):
            raise ValueError(f"{self.type} content requires a {key} array")
        return self


class VerificationDifference(StrictModel):
    id: uuid.UUID
    category: Literal["MISSING", "EXTRA", "VALUE", "TIMING", "LAYOUT", "OTHER"]
    target: str = Field(min_length=1)
    description: str = Field(min_length=1)
    expected: str | None = None
    actual: str | None = None


class CorrectionSuggestion(StrictModel):
    id: uuid.UUID
    diff_id: uuid.UUID | None = None
    target: str = Field(min_length=1)
    instruction: str = Field(min_length=1)


class VerifyOutput(StrictModel):
    match: Literal["TRUE", "PARTIAL", "FALSE"]
    summary: str = Field(min_length=1)
    checked_at: AwareDatetime | None = None
    checked_at_display: str | None = None
    diff_count: int | None = Field(default=None, ge=0)
    diffs: list[VerificationDifference] | None = None
    suggestions: list[CorrectionSuggestion] | None = None

    @model_validator(mode="after")
    def differences_are_consistent(self):
        if self.diffs is not None:
            ids = [diff.id for diff in self.diffs]
            if len(ids) != len(set(ids)):
                raise ValueError("duplicate difference id")
            if self.diff_count is not None and self.diff_count != len(self.diffs):
                raise ValueError("diff_count must match the supplied complete differences")
            if any(s.diff_id is not None and s.diff_id not in ids for s in self.suggestions or []):
                raise ValueError("suggestion references an unknown difference")
        suggestion_ids = [s.id for s in self.suggestions or []]
        if len(suggestion_ids) != len(set(suggestion_ids)):
            raise ValueError("duplicate suggestion id")
        if self.match == "TRUE" and (self.diff_count not in (None, 0) or self.diffs):
            raise ValueError("TRUE verification cannot contain differences")
        return self


class StepError(StrictModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)


class StepBase(StrictModel):
    id: uuid.UUID
    sequence: int = Field(ge=1)
    input_step_id: uuid.UUID | None
    status: Literal["PENDING", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"]
    created_at: AwareDatetime
    started_at: AwareDatetime | None = None
    finished_at: AwareDatetime | None = None
    error: StepError | None = None

    @model_validator(mode="after")
    def output_matches_status(self):
        if self.status == "SUCCEEDED":
            if self.output is None or self.error is not None:
                raise ValueError("successful steps require output and no error")
        elif self.output is not None:
            raise ValueError("only successful steps carry output")
        if self.status == "FAILED" and self.error is None:
            raise ValueError("failed steps require error")
        if self.status != "FAILED" and self.error is not None:
            raise ValueError("only failed steps carry error")
        return self


class DrawerStep(StepBase):
    type: Literal["DRAWER"]
    output: DrawerOutput | None = None


class VerifyStep(StepBase):
    type: Literal["VERIFY"]
    output: VerifyOutput | None = None


ResultStep = Annotated[DrawerStep | VerifyStep, Field(discriminator="type")]


class ResultFlow(StrictModel):
    schema_version: Literal[1] = 1
    steps: list[ResultStep] = Field(default_factory=list)
    final_drawer_step_id: uuid.UUID | None = None
    final_verify_step_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def chain_is_consistent(self):
        seen = set()
        previous = None
        for number, step in enumerate(self.steps, start=1):
            if step.id in seen or step.sequence != number:
                raise ValueError("step ids must be unique and sequence contiguous from 1")
            seen.add(step.id)
            expected_type = "DRAWER" if number % 2 else "VERIFY"
            if step.type != expected_type:
                raise ValueError("steps must alternate DRAWER then VERIFY")
            if step.input_step_id != (previous.id if previous else None):
                raise ValueError("each step must reference its immediate predecessor")
            if previous is not None and previous.status != "SUCCEEDED":
                raise ValueError("only a successful predecessor may have a following step")
            if isinstance(step, DrawerStep) and step.output is not None:
                known = {s.id for s in previous.output.suggestions or []} if previous else set()
                if any(c.suggestion_id is not None and c.suggestion_id not in known
                       for c in step.output.changes):
                    raise ValueError("change references an unknown preceding suggestion")
            previous = step
        by_id = {step.id: step for step in self.steps}
        drawer = by_id.get(self.final_drawer_step_id)
        verifier = by_id.get(self.final_verify_step_id)
        if self.final_drawer_step_id is not None:
            if not isinstance(drawer, DrawerStep) or drawer.status != "SUCCEEDED":
                raise ValueError("final drawer must reference a successful DRAWER")
        if self.final_verify_step_id is not None:
            if not isinstance(verifier, VerifyStep) or verifier.status != "SUCCEEDED":
                raise ValueError("final verification must reference a successful VERIFY")
            if drawer is None or verifier.input_step_id != drawer.id:
                raise ValueError("final verification must verify the final drawer")
        return self
