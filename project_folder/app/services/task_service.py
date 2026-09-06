"""Business logic for 建立/查詢/更新/中斷/刪除任務 (demo step 2, 9)."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AnalysisTaskStatus, ExecutionStatus, TaskDisplayStatus
from app.core.exceptions import ConflictError, NotFoundError
from app.models.analysis_task import AnalysisTask
from app.repositories.analysis_task_repository import AnalysisTaskRepository
from app.repositories.execution_repository import ExecutionRepository
from app.repositories.parse_item_repository import ParseItemRepository
from app.repositories.result_repository import ResultRepository
from app.schemas.execution import ExecutionOut
from app.schemas.task import (
    TaskCreate,
    TaskDetail,
    TaskItemDetail,
    TaskListItem,
    TaskOut,
    TaskProgress,
    TaskUpdate,
)
from app.services import execution_service
from app.services.parse_item_service import to_out as parse_item_to_out
from app.utils.datetime import utcnow
from app.services.workbench_service import public_result

EDITABLE_TASK_STATUSES = (
    AnalysisTaskStatus.DRAFT.value,
    AnalysisTaskStatus.READY.value,
)
ACTIVE_TASK_STATUSES = (
    AnalysisTaskStatus.DISPATCHED.value,
    AnalysisTaskStatus.RUNNING.value,
)
TERMINAL_TASK_STATUSES = (
    AnalysisTaskStatus.COMPLETED.value,
    AnalysisTaskStatus.CANCELLED.value,
    AnalysisTaskStatus.FAILED.value,
)


def _build_progress(item_count: int, status_counts: dict[str, int]) -> TaskProgress:
    pending = status_counts.get(ExecutionStatus.CREATED.value, 0) + status_counts.get(
        ExecutionStatus.QUEUED.value, 0
    )
    running = status_counts.get(ExecutionStatus.RUNNING.value, 0)
    succeeded = status_counts.get(ExecutionStatus.SUCCEEDED.value, 0)
    failed = status_counts.get(ExecutionStatus.FAILED.value, 0) + status_counts.get(
        ExecutionStatus.TIMEOUT.value, 0
    )
    cancelled = status_counts.get(ExecutionStatus.CANCELLED.value, 0)

    finished = succeeded + failed + cancelled
    percent = round(finished / item_count * 100) if item_count else 0

    return TaskProgress(
        item_count=item_count,
        pending=pending,
        running=running,
        succeeded=succeeded,
        failed=failed,
        cancelled=cancelled,
        percent=percent,
    )


def _display_status(task: AnalysisTask, progress: TaskProgress) -> str:
    """Collapse stored status + live counts into what 任務總覽 shows.

    The counts win over the stored status once a task is dispatched: freeze §7 keeps
    progress out of the table, so `analysis_task.status` can lag behind its executions.
    """
    if task.status == AnalysisTaskStatus.CANCELLED.value:
        return TaskDisplayStatus.CANCELLED.value
    if task.status == AnalysisTaskStatus.FAILED.value:
        return TaskDisplayStatus.FAILED.value
    if task.status in (AnalysisTaskStatus.DRAFT.value, AnalysisTaskStatus.READY.value):
        return TaskDisplayStatus.PENDING.value

    finished = progress.succeeded + progress.failed + progress.cancelled
    if progress.item_count and finished >= progress.item_count:
        return (
            TaskDisplayStatus.FAILED.value
            if progress.failed
            else TaskDisplayStatus.COMPLETED.value
        )
    if progress.running or finished:
        return TaskDisplayStatus.RUNNING.value
    if task.status == AnalysisTaskStatus.COMPLETED.value:
        return TaskDisplayStatus.COMPLETED.value
    return TaskDisplayStatus.PENDING.value


def _to_out(task: AnalysisTask, progress: TaskProgress) -> TaskOut:
    return TaskOut(
        id=task.id,
        name=task.name,
        description=task.description,
        status=task.status,
        display_status=_display_status(task, progress),
        config=task.config or {},
        dispatched_at=task.dispatched_at,
        completed_at=task.completed_at,
        created_at=task.created_at,
        updated_at=task.updated_at,
        progress=progress,
    )


async def _with_progress(session: AsyncSession, tasks: list[AnalysisTask]) -> list[TaskOut]:
    """One aggregate query for the whole page, not one per task."""
    repo = AnalysisTaskRepository(session)
    task_ids = [task.id for task in tasks]
    item_counts = await repo.item_counts(task_ids)
    status_counts = await repo.execution_status_counts(task_ids)

    return [
        _to_out(
            task,
            _build_progress(item_counts.get(task.id, 0), status_counts.get(task.id, {})),
        )
        for task in tasks
    ]


async def create_task(session: AsyncSession, user_id: uuid.UUID, payload: TaskCreate) -> TaskOut:
    task = AnalysisTask(
        user_id=user_id,
        name=payload.name,
        description=payload.description,
        status=AnalysisTaskStatus.DRAFT.value,
        config=payload.config,
    )
    session.add(task)
    await session.commit()
    return _to_out(task, _build_progress(0, {}))


def _overview_status(task: AnalysisTask, progress: TaskProgress) -> str:
    """One overview status; DRAFT remains distinguishable for frontend statistics."""
    if task.status in (AnalysisTaskStatus.DRAFT.value, AnalysisTaskStatus.READY.value):
        return task.status
    if task.status == AnalysisTaskStatus.CANCELLED.value:
        return AnalysisTaskStatus.CANCELLED.value
    if task.status == AnalysisTaskStatus.FAILED.value:
        return AnalysisTaskStatus.FAILED.value
    finished = progress.succeeded + progress.failed + progress.cancelled
    if progress.item_count and finished >= progress.item_count:
        if progress.failed:
            return AnalysisTaskStatus.FAILED.value
        if progress.cancelled:
            return AnalysisTaskStatus.CANCELLED.value
        return AnalysisTaskStatus.COMPLETED.value
    if progress.running or finished:
        return AnalysisTaskStatus.RUNNING.value
    if progress.pending:
        return AnalysisTaskStatus.DISPATCHED.value
    return task.status


async def list_tasks(session: AsyncSession, user_id: uuid.UUID) -> list[TaskListItem]:
    repo = AnalysisTaskRepository(session)
    tasks = await repo.list_for_user(user_id)
    task_ids = [task.id for task in tasks]
    item_counts = await repo.item_counts(task_ids)
    status_counts = await repo.execution_status_counts(task_ids, eligible_only=True)
    activity = await repo.activity_times(task_ids)
    items = []
    for task in tasks:
        progress = _build_progress(item_counts.get(task.id, 0), status_counts.get(task.id, {}))
        started_at, child_updated_at = activity.get(task.id, (None, None))
        updated_at = max(task.updated_at, child_updated_at) if child_updated_at else task.updated_at
        items.append(TaskListItem(
            id=task.id,
            name=task.name,
            status=_overview_status(task, progress),
            finished_count=progress.succeeded + progress.failed + progress.cancelled,
            started_at=started_at,
            updated_at=updated_at,
            item_count=progress.item_count,
        ))
    return sorted(items, key=lambda item: (item.updated_at, str(item.id)), reverse=True)


async def get_task(session: AsyncSession, user_id: uuid.UUID, task_id: uuid.UUID) -> TaskOut:
    task = await AnalysisTaskRepository(session).get_owned(task_id, user_id)
    if task is None:
        raise NotFoundError("Task not found")
    return (await _with_progress(session, [task]))[0]


async def update_task(
    session: AsyncSession, user_id: uuid.UUID, task_id: uuid.UUID, payload: TaskUpdate
) -> TaskOut:
    task = await AnalysisTaskRepository(session).get_owned(task_id, user_id)
    if task is None:
        raise NotFoundError("Task not found")

    # 任務名稱 and 任務整體備註 are plain metadata — editable at any status, including
    # from the detail view of a finished task. `config` is not: it was snapshotted into
    # every execution at dispatch, so changing it afterwards would describe a run that
    # never happened.
    if payload.config is not None and task.status not in EDITABLE_TASK_STATUSES:
        raise ConflictError(
            f"Task in status {task.status} can no longer change its config",
            error_code="TASK_CONFIG_FROZEN",
        )

    if payload.name is not None:
        task.name = payload.name
    if payload.description is not None:
        task.description = payload.description
    if payload.config is not None:
        task.config = payload.config

    await session.commit()
    return (await _with_progress(session, [task]))[0]


async def get_task_detail(
    session: AsyncSession, user_id: uuid.UUID, task_id: uuid.UUID
) -> TaskDetail:
    """主任務 + 其下所有子任務（ROI、最新一次執行、目前的最終解析程式）。

    Three batched queries for the whole subtask list rather than per-item lookups.
    """
    task = await AnalysisTaskRepository(session).get_owned(task_id, user_id)
    if task is None:
        raise NotFoundError("Task not found")

    task_out = (await _with_progress(session, [task]))[0]
    rows = await ParseItemRepository(session).list_for_task(task_id)

    parse_item_ids = [parse_item.id for parse_item, _ in rows]
    latest_executions = await ExecutionRepository(session).latest_for_parse_items(parse_item_ids)

    execution_ids = [execution.id for execution in latest_executions.values()]
    latest_results = await ResultRepository(session).latest_for_executions(execution_ids)
    round_counts = await ResultRepository(session).counts_for_executions(execution_ids)

    items = []
    for parse_item, asset_file_name in rows:
        execution = latest_executions.get(parse_item.id)
        result = latest_results.get(execution.id) if execution else None
        items.append(
            TaskItemDetail(
                parse_item=parse_item_to_out(parse_item, asset_file_name),
                latest_execution=ExecutionOut.model_validate(execution) if execution else None,
                result_round_count=round_counts.get(execution.id, 0) if execution else 0,
                latest_result=public_result(result) if result else None,
            )
        )

    return TaskDetail(task=task_out, items=items)


async def cancel_task(session: AsyncSession, user_id: uuid.UUID, task_id: uuid.UUID) -> TaskOut:
    """中斷：stop everything still cancellable, then park the task in CANCELLED."""
    task = await AnalysisTaskRepository(session).get_owned_for_update(task_id, user_id)
    if task is None:
        raise NotFoundError("Task not found")

    if task.status in TERMINAL_TASK_STATUSES:
        raise ConflictError(
            f"Task in status {task.status} cannot be cancelled",
            error_code="TASK_NOT_CANCELLABLE",
        )

    await execution_service.cancel_executions_of_task(session, task_id)
    task.status = AnalysisTaskStatus.CANCELLED.value
    # completed_at means "reached a terminal state"; status distinguishes 完成 from 中斷.
    task.completed_at = utcnow()
    await session.commit()

    return (await _with_progress(session, [task]))[0]


async def delete_task(session: AsyncSession, user_id: uuid.UUID, task_id: uuid.UUID) -> None:
    """Soft delete. An in-flight task must be cancelled first, so no worker is left
    writing results into a task the user believes is gone."""
    repo = AnalysisTaskRepository(session)
    task = await repo.get_owned_for_update(task_id, user_id)

    if task is None:
        # Already soft-deleted is idempotent; never-existing or someone else's is a 404.
        existing = await repo.get_any_owned(task_id, user_id)
        if existing is None:
            raise NotFoundError("Task not found")
        return

    if task.status in ACTIVE_TASK_STATUSES:
        raise ConflictError(
            "Cancel the task before deleting it",
            error_code="TASK_STILL_ACTIVE",
        )

    task.deleted_at = utcnow()
    await session.commit()
