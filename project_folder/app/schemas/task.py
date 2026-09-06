import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.execution import ExecutionOut
from app.schemas.parse_item import ParseItemOut
from app.schemas.result import ResultOut


class TaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    config: dict = Field(default_factory=dict)


class TaskUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    config: dict | None = None


class TaskProgress(BaseModel):
    """Aggregated live from parse_item / execution — freeze §7 forbids storing these."""

    item_count: int
    pending: int
    running: int
    succeeded: int
    failed: int
    cancelled: int
    percent: int


class TaskOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    status: str
    #: 等待 / 執行中 / 錯誤 / 完成 / 已中斷 — derived, see core.enums.TaskDisplayStatus
    display_status: str
    config: dict
    dispatched_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    progress: TaskProgress


class TaskListItem(BaseModel):
    """Compact overview for one analysis_task; list responses are not paginated."""

    id: uuid.UUID
    name: str
    status: str
    finished_count: int
    started_at: datetime | None
    updated_at: datetime
    item_count: int


class TaskListResponse(BaseModel):
    items: list[TaskListItem]


class TaskItemDetail(BaseModel):
    """One 子任務: its ROI, the newest run, and the current 最終解析程式."""

    parse_item: ParseItemOut
    latest_execution: ExecutionOut | None
    result_round_count: int
    latest_result: ResultOut | None


class TaskDetail(BaseModel):
    task: TaskOut
    items: list[TaskItemDetail]
