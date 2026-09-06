"""Internal result writer for a future worker/importer. No public upload endpoint.

Caller owns the transaction and execution lifecycle. Artifact files must already
exist under the supplied result ID; do not commit here or overwrite prior results.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ExecutionStatus, ResultStatus
from app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.models.execution import Execution
from app.models.result import Result
from app.repositories.result_repository import ResultRepository
from app.schemas.workbench import WorkbenchData
from app.services.workbench_service import content_digest
from app.utils import storage


async def record_generated_result(
    session: AsyncSession, *, execution_id: uuid.UUID, result_id: uuid.UUID,
    content: str, parse_type: str, content_type: str,
    workbench: WorkbenchData, note: str | None = None,
) -> Result:
    query = await session.execute(
        select(Execution).where(Execution.id == execution_id).with_for_update()
    )
    execution = query.scalar_one_or_none()
    if execution is None:
        raise NotFoundError("Execution not found")
    if execution.status != ExecutionStatus.RUNNING.value:
        raise ConflictError("Only a running execution may write generated results",
                            error_code="EXECUTION_NOT_RUNNING")
    if not content.strip() or workbench.content_sha256 != content_digest(content):
        raise ValidationAppError("Workbench content digest mismatch", error_code="STALE_WORKBENCH")
    repository = ResultRepository(session)
    if await repository.get_by_id(result_id) is not None:
        raise ConflictError("Result ID already exists", error_code="RESULT_EXISTS")

    references = {v.result_id for v in workbench.render_versions if v.result_id}
    references.update(r.input_result_id for r in workbench.verification.rounds if r.input_result_id)
    for reference in references - {result_id}:
        prior = await repository.get_by_id(reference)
        if prior is None or prior.execution_id != execution_id:
            raise ValidationAppError("Referenced result belongs to another execution",
                                     error_code="INVALID_RESULT_REFERENCE")
    prefix = f"results/{execution_id}/{result_id}/"
    root = storage.resolve(prefix)
    for artifact in workbench.artifacts:
        try:
            path = storage.resolve(artifact.storage_key)
        except ValueError:
            raise ValidationAppError("Invalid artifact path", error_code="INVALID_ARTIFACT") from None
        if not artifact.storage_key.startswith(prefix) or root not in path.parents or not path.is_file():
            raise ValidationAppError("Artifact must exist inside this result directory",
                                     error_code="INVALID_ARTIFACT")

    result = Result(
        id=result_id, execution_id=execution_id,
        round_no=await repository.next_round_no(execution_id),
        status=ResultStatus.SUCCEEDED.value,
        result_info={
            "schema_version": 2, "type": parse_type, "content_type": content_type,
            "content": content, "source": "AI", "note": note,
            "workbench": workbench.model_dump(mode="json"),
        },
    )
    session.add(result)
    await session.flush()
    return result
