"""最終解析程式 的讀取與編輯.

Editing never overwrites. Each save appends the next `round_no` of the parse item's
latest execution, so `core.result` keeps the whole version history (v01 / v02 / 最終)
exactly as the report renders it.
"""

import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ResultStatus
from app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.models.result import Result
from app.repositories.execution_repository import NON_TERMINAL_STATUSES, ExecutionRepository
from app.repositories.parse_item_repository import ParseItemRepository
from app.repositories.result_repository import ResultRepository
from app.schemas.result import ResultAppend, ResultOut
from app.utils.datetime import utcnow
from app.schemas.workbench import WorkbenchData
from app.services.workbench_service import content_digest, public_result

MANUAL_SOURCE = "MANUAL"


async def _latest_execution_id(
    session: AsyncSession, user_id: uuid.UUID, parse_item_id: uuid.UUID, *, lock: bool
) -> uuid.UUID:
    owned = await ParseItemRepository(session).get_owned(parse_item_id, user_id)
    if owned is None:
        raise NotFoundError("Parse item not found")

    repo = ExecutionRepository(session)
    if lock:
        execution = await repo.get_latest_for_parse_item_for_update(parse_item_id)
    else:
        latest = await repo.latest_for_parse_items([parse_item_id])
        execution = latest.get(parse_item_id)

    if execution is None:
        raise ConflictError(
            "Parse item has not been dispatched yet, so it has no parse result",
            error_code="NO_EXECUTION",
        )
    return execution.id


async def list_results(
    session: AsyncSession, user_id: uuid.UUID, parse_item_id: uuid.UUID
) -> list[ResultOut]:
    execution_id = await _latest_execution_id(session, user_id, parse_item_id, lock=False)
    rounds = await ResultRepository(session).list_for_execution(execution_id)
    return [public_result(row) for row in rounds]


async def append_result(
    session: AsyncSession,
    user_id: uuid.UUID,
    parse_item_id: uuid.UUID,
    payload: ResultAppend,
) -> ResultOut:
    # The lock is what makes round_no safe: it is unique per execution, so two
    # concurrent saves must not both read the same max().
    execution_id = await _latest_execution_id(session, user_id, parse_item_id, lock=True)

    execution = await ExecutionRepository(session).get_owned(execution_id, user_id)
    if payload.execution_id is not None and payload.execution_id != execution_id:
        raise ConflictError("Execution has changed; reload before saving", error_code="EXECUTION_CHANGED")
    if execution.status in NON_TERMINAL_STATUSES:
        raise ConflictError("Execution is still active", error_code="EXECUTION_STILL_ACTIVE")

    repo = ResultRepository(session)
    previous = await repo.latest_for_executions([execution_id])
    previous_result = previous.get(execution_id)
    if previous_result is None:
        raise ConflictError("No result to edit", error_code="NO_RESULT")
    if payload.base_result_id is not None and payload.base_result_id != previous_result.id:
        raise ConflictError("Result has changed; reload before saving", error_code="RESULT_VERSION_CONFLICT")
    previous_info = previous_result.result_info or {}
    content_type = payload.content_type or previous_info.get("content_type")
    if content_type and content_type.upper() == "WAVEDROM":
        try:
            content = json.loads(payload.content)
        except (ValueError, TypeError):
            raise ValidationAppError("Invalid WaveDrom JSON", error_code="INVALID_RESULT_CONTENT") from None
        if not isinstance(content, dict) or not (
            isinstance(content.get("signal"), list) or isinstance(content.get("reg"), list)
        ):
            raise ValidationAppError("WaveDrom requires signal or reg", error_code="INVALID_RESULT_CONTENT")
    # Empty derived outputs are deliberate: editing content invalidates all previous
    # render images, verification summaries and Verilog conversions.
    workbench = WorkbenchData(content_sha256=content_digest(payload.content))

    result = Result(
        execution_id=execution_id,
        round_no=await repo.next_round_no(execution_id),
        status=ResultStatus.SUCCEEDED.value,
        result_info={
            # Carry the classification forward so a content-only edit keeps its type.
            "type": payload.type or previous_info.get("type"),
            "content_type": content_type,
            "content": payload.content,
            "schema_version": 2,
            "base_result_id": str(previous_result.id),
            "workbench": workbench.model_dump(mode="json"),
            "source": MANUAL_SOURCE,
            "note": payload.note,
            "edited_by": str(user_id),
            "edited_at": utcnow().isoformat(),
        },
    )
    session.add(result)
    await session.commit()

    return public_result(result)
