"""ROI 匡選與暫存 (step 03A): build and maintain a task's parse list.

The parse list is frozen once the task is dispatched — after that, changing an ROI would
silently disagree with the input snapshot already handed to the queue.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AnalysisTaskStatus, AssetFileType, ParseItemStatus
from app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.models.analysis_task import AnalysisTask
from app.models.asset import Asset
from app.models.parse_item import ParseItem
from app.repositories.analysis_task_repository import AnalysisTaskRepository
from app.repositories.asset_repository import AssetRepository
from app.repositories.execution_repository import ExecutionRepository
from app.repositories.outbox_event_repository import OutboxEventRepository
from app.repositories.parse_item_repository import ParseItemRepository
from app.schemas.parse_item import ParseItemBulkCreate, ParseItemOut, ParseItemUpdate
from app.utils.datetime import utcnow
from app.utils.roi import is_valid_roi

EDITABLE_TASK_STATUSES = (
    AnalysisTaskStatus.DRAFT.value,
    AnalysisTaskStatus.READY.value,
)


def to_out(parse_item: ParseItem, asset_file_name: str) -> ParseItemOut:
    return ParseItemOut(
        id=parse_item.id,
        task_id=parse_item.task_id,
        asset_id=parse_item.asset_id,
        asset_file_name=asset_file_name,
        name=parse_item.name,
        status=parse_item.status,
        page_no=parse_item.page_no,
        x=parse_item.x,
        y=parse_item.y,
        width=parse_item.width,
        height=parse_item.height,
        created_at=parse_item.created_at,
    )


def _assert_editable(task: AnalysisTask) -> None:
    if task.status not in EDITABLE_TASK_STATUSES:
        raise ConflictError(
            f"Task in status {task.status} has a frozen parse list",
            error_code="PARSE_LIST_FROZEN",
        )


async def _load_editable_task(
    session: AsyncSession, user_id: uuid.UUID, task_id: uuid.UUID
) -> AnalysisTask:
    task = await AnalysisTaskRepository(session).get_owned(task_id, user_id)
    if task is None:
        raise NotFoundError("Task not found")
    _assert_editable(task)
    return task


def _validate_page_no(asset: Asset, page_no: int, *, prefix: str = "") -> None:
    """Use the same known PDF page-count bound for create and update."""
    page_count = (asset.attributes or {}).get("page_count")
    if (
        asset.file_type == AssetFileType.PDF.value
        and isinstance(page_count, int)
        and page_no > page_count
    ):
        raise ValidationAppError(
            f"{prefix}page_no {page_no} exceeds the asset's {page_count} pages",
            error_code="PAGE_OUT_OF_RANGE",
        )


async def create_parse_items(
    session: AsyncSession,
    user_id: uuid.UUID,
    task_id: uuid.UUID,
    payload: ParseItemBulkCreate,
) -> list[ParseItemOut]:
    await _load_editable_task(session, user_id, task_id)

    asset_repo = AssetRepository(session)
    asset_cache: dict[uuid.UUID, Asset] = {}
    created: list[tuple[ParseItem, str]] = []

    for index, item in enumerate(payload.items):
        if not is_valid_roi(item.x, item.y, item.width, item.height):
            raise ValidationAppError(
                f"items[{index}]: ROI outside the normalized 0..1 range",
                error_code="INVALID_ROI",
            )

        asset = asset_cache.get(item.asset_id)
        if asset is None:
            asset = await asset_repo.get_owned(item.asset_id, user_id)
            if asset is None:
                raise NotFoundError(f"items[{index}]: asset not found")
            asset_cache[item.asset_id] = asset

        _validate_page_no(asset, item.page_no, prefix=f"items[{index}]: ")

        parse_item = ParseItem(
            task_id=task_id,
            asset_id=item.asset_id,
            name=item.name,
            status=ParseItemStatus.DRAFT.value,
            page_no=item.page_no,
            x=item.x,
            y=item.y,
            width=item.width,
            height=item.height,
        )
        session.add(parse_item)
        created.append((parse_item, asset.file_name))

    await session.commit()
    return [to_out(parse_item, file_name) for parse_item, file_name in created]


async def list_parse_items(
    session: AsyncSession, user_id: uuid.UUID, task_id: uuid.UUID
) -> list[ParseItemOut]:
    task = await AnalysisTaskRepository(session).get_owned(task_id, user_id)
    if task is None:
        raise NotFoundError("Task not found")

    rows = await ParseItemRepository(session).list_for_task(task_id)
    return [to_out(parse_item, file_name) for parse_item, file_name in rows]


async def get_parse_item(
    session: AsyncSession, user_id: uuid.UUID, parse_item_id: uuid.UUID
) -> ParseItemOut:
    owned = await ParseItemRepository(session).get_owned(parse_item_id, user_id)
    if owned is None:
        raise NotFoundError("Parse item not found")

    parse_item, _, asset_file_name = owned
    return to_out(parse_item, asset_file_name)


async def update_parse_item(
    session: AsyncSession,
    user_id: uuid.UUID,
    parse_item_id: uuid.UUID,
    payload: ParseItemUpdate,
) -> ParseItemOut:
    repo = ParseItemRepository(session)
    owned = await repo.get_owned(parse_item_id, user_id)
    if owned is None:
        raise NotFoundError("Parse item not found")

    parse_item, task, asset_file_name = owned
    _assert_editable(task)

    allowed_statuses = {status.value for status in ParseItemStatus}
    if payload.status is not None and payload.status not in allowed_statuses:
        raise ValidationAppError(
            f"status must be one of {sorted(allowed_statuses)}", error_code="INVALID_STATUS"
        )

    new_x = payload.x if payload.x is not None else parse_item.x
    new_y = payload.y if payload.y is not None else parse_item.y
    new_width = payload.width if payload.width is not None else parse_item.width
    new_height = payload.height if payload.height is not None else parse_item.height

    if not is_valid_roi(new_x, new_y, new_width, new_height):
        raise ValidationAppError(
            "ROI outside the normalized 0..1 range", error_code="INVALID_ROI"
        )

    if payload.page_no is not None:
        # Existing tasks retain their source even if it was soft-deleted from the
        # file library. Ownership of the parse item/task was checked above.
        asset = await AssetRepository(session).get_by_id(parse_item.asset_id)
        if asset is None or asset.user_id != user_id:
            raise NotFoundError("Source not found")
        _validate_page_no(asset, payload.page_no)

    parse_item.x, parse_item.y = new_x, new_y
    parse_item.width, parse_item.height = new_width, new_height
    if payload.name is not None:
        parse_item.name = payload.name
    if payload.status is not None:
        parse_item.status = payload.status
    if payload.page_no is not None:
        parse_item.page_no = payload.page_no

    await session.commit()
    return to_out(parse_item, asset_file_name)


async def delete_parse_item(
    session: AsyncSession, user_id: uuid.UUID, parse_item_id: uuid.UUID
) -> None:
    """刪除子任務 — soft, and allowed at any task status.

    A hard delete would cascade through execution → result / agent_run and destroy the
    parse history the report is built from. Anything still running for this subtask is
    cancelled first, so no worker keeps writing into a subtask the user removed.
    """
    repo = ParseItemRepository(session)
    owned = await repo.get_owned(parse_item_id, user_id)

    if owned is None:
        existing = await repo.get_any_owned(parse_item_id, user_id)
        if existing is None:
            raise NotFoundError("Parse item not found")
        return  # already soft-deleted -> idempotent 204

    parse_item, _, _ = owned

    cancelled_ids = await ExecutionRepository(session).cancel_non_terminal_for_parse_items(
        [parse_item.id]
    )
    await OutboxEventRepository(session).abandon_pending_for_executions(cancelled_ids)

    parse_item.deleted_at = utcnow()
    await session.commit()
