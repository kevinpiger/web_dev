"""Dispatch (送出任務) and cancellation (中斷).

Dispatch stops at the transactional outbox: executions and their `EXECUTION_CREATED`
outbox rows are written in one transaction, and a later publisher stage moves them to
RabbitMQ. Nothing here talks to a broker.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    AnalysisTaskStatus,
    ExecutionStatus,
    OutboxEventStatus,
    OutboxEventType,
    ParseItemStatus,
)
from app.core.exceptions import ConflictError, NotFoundError
from app.models.analysis_task import AnalysisTask
from app.models.execution import Execution
from app.models.outbox_event import OutboxEvent
from app.models.parse_item import ParseItem
from app.repositories.analysis_task_repository import AnalysisTaskRepository
from app.repositories.execution_repository import NON_TERMINAL_STATUSES, ExecutionRepository
from app.repositories.outbox_event_repository import OutboxEventRepository
from app.repositories.parse_item_repository import ParseItemRepository
from app.schemas.execution import CancelResult, DispatchResult, ExecutionOut
from app.utils.datetime import utcnow

DEFAULT_MAX_RETRY_COUNT = 3

DISPATCHABLE_TASK_STATUSES = (
    AnalysisTaskStatus.DRAFT.value,
    AnalysisTaskStatus.READY.value,
)


def _build_execution(task: AnalysisTask, parse_item: ParseItem) -> Execution:
    config = task.config or {}
    return Execution(
        parse_id=parse_item.id,
        status=ExecutionStatus.CREATED.value,
        retry_count=0,
        max_retry_count=int(config.get("max_retry_count", DEFAULT_MAX_RETRY_COUNT)),
        flow_id=config.get("flow_id"),
        flow_version=config.get("flow_version"),
        model_id=config.get("model_id"),
        model_version=config.get("model_version"),
        # Snapshot of the inputs at dispatch time (freeze §9) — later edits to the
        # parse item or task config must not change what this run was asked to do.
        input_data={
            "asset_id": str(parse_item.asset_id),
            "page_no": parse_item.page_no,
            "roi": {
                "x": parse_item.x,
                "y": parse_item.y,
                "width": parse_item.width,
                "height": parse_item.height,
            },
            "config": config,
        },
    )


async def dispatch_task(
    session: AsyncSession, user_id: uuid.UUID, task_id: uuid.UUID
) -> DispatchResult:
    task_repo = AnalysisTaskRepository(session)
    task = await task_repo.get_owned_for_update(task_id, user_id)
    if task is None:
        raise NotFoundError("Task not found")

    if task.status not in DISPATCHABLE_TASK_STATUSES:
        raise ConflictError(
            f"Task in status {task.status} cannot be dispatched",
            error_code="TASK_NOT_DISPATCHABLE",
        )

    parse_items = await ParseItemRepository(session).list_dispatchable_for_task(task_id)
    if not parse_items:
        raise ConflictError("沒有可派送的項目", error_code="NO_PARSE_ITEM")

    # Promote drafts in the same transaction as executions and outbox events.
    for parse_item in parse_items:
        if parse_item.status == ParseItemStatus.DRAFT.value:
            parse_item.status = ParseItemStatus.READY.value

    executions = [_build_execution(task, parse_item) for parse_item in parse_items]
    session.add_all(executions)
    await session.flush()  # assign execution ids before the outbox rows reference them

    now = utcnow()
    session.add_all(
        OutboxEvent(
            execution_id=execution.id,
            event_type=OutboxEventType.EXECUTION_CREATED.value,
            status=OutboxEventStatus.PENDING.value,
            retry_count=0,
            available_at=now,
        )
        for execution in executions
    )

    task.status = AnalysisTaskStatus.DISPATCHED.value
    task.dispatched_at = now
    await session.commit()

    return DispatchResult(
        task_id=task.id,
        task_status=task.status,
        dispatched_count=len(executions),
        executions=[ExecutionOut.model_validate(execution) for execution in executions],
    )


async def cancel_executions_of_task(session: AsyncSession, task_id: uuid.UUID) -> int:
    """Cancel every still-cancellable execution of a task and abandon its pending events.

    Caller owns the transaction — task_service commits once the task row is updated too.
    """
    parse_item_ids = await ParseItemRepository(session).ids_for_task(task_id)
    cancelled_ids = await ExecutionRepository(session).cancel_non_terminal_for_parse_items(
        parse_item_ids
    )
    await OutboxEventRepository(session).abandon_pending_for_executions(cancelled_ids)
    return len(cancelled_ids)


async def cancel_execution(
    session: AsyncSession, user_id: uuid.UUID, execution_id: uuid.UUID
) -> CancelResult:
    repo = ExecutionRepository(session)
    execution = await repo.get_owned_for_update(execution_id, user_id)
    if execution is None:
        raise NotFoundError("Execution not found")

    if execution.status not in NON_TERMINAL_STATUSES:
        raise ConflictError(
            f"Execution in status {execution.status} cannot be cancelled",
            error_code="EXECUTION_NOT_CANCELLABLE",
        )

    execution.status = ExecutionStatus.CANCELLED.value
    execution.finished_at = utcnow()
    await OutboxEventRepository(session).abandon_pending_for_executions([execution.id])
    await session.commit()

    return CancelResult(cancelled_executions=1)


async def list_executions(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    page: int,
    page_size: int,
    task_id: uuid.UUID | None,
    parse_id: uuid.UUID | None,
    status: str | None,
) -> tuple[list[ExecutionOut], int]:
    executions, total = await ExecutionRepository(session).list_for_user(
        user_id,
        page=page,
        page_size=page_size,
        task_id=task_id,
        parse_id=parse_id,
        status=status,
    )
    return [ExecutionOut.model_validate(execution) for execution in executions], total


async def get_execution(
    session: AsyncSession, user_id: uuid.UUID, execution_id: uuid.UUID
) -> ExecutionOut:
    execution = await ExecutionRepository(session).get_owned(execution_id, user_id)
    if execution is None:
        raise NotFoundError("Execution not found")
    return ExecutionOut.model_validate(execution)
