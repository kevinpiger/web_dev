"""Read a parse item's workbench, with ownership checked through the parent task."""
import hashlib
import logging
import uuid

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import NotFoundError
from app.models.result import Result
from app.repositories.asset_repository import AssetRepository
from app.repositories.execution_repository import ExecutionRepository
from app.repositories.parse_item_repository import ParseItemRepository
from app.repositories.result_repository import ResultRepository
from app.schemas.execution import ExecutionOut
from app.schemas.result import ResultOut
from app.schemas.workbench import (
    ArtifactOut, WorkbenchData, WorkbenchOut, WorkbenchSource,
)
from app.services.parse_item_service import to_out as parse_item_to_out
from app.utils import storage

logger = logging.getLogger(__name__)


def content_digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def read_workbench_data(result: Result) -> tuple[str, WorkbenchData | None]:
    info = result.result_info or {}
    raw = info.get("workbench")
    if raw is None:
        return "LEGACY", None
    try:
        data = WorkbenchData.model_validate(raw)
    except ValidationError:
        logger.warning("invalid workbench payload for result %s", result.id)
        return "INVALID", None
    content = info.get("content")
    if not isinstance(content, str) or data.content_sha256 != content_digest(content):
        return "STALE", None
    return "AVAILABLE", data


def public_result(result: Result) -> ResultOut:
    # Nested workbench data is returned separately; do not expose storage keys or
    # duplicate all images/metrics in every result row.
    value = ResultOut.model_validate(result)
    value.result_info = {k: v for k, v in (result.result_info or {}).items() if k != "workbench"}
    return value


def artifact_out(result_id: uuid.UUID, artifact) -> ArtifactOut:
    return ArtifactOut(
        id=artifact.id,
        media_type=artifact.media_type,
        content_url=f"{settings.API_PREFIX}/results/{result_id}/artifacts/{artifact.id}/content",
    )


async def get_workbench(
    session: AsyncSession, user_id: uuid.UUID, parse_id: uuid.UUID,
    *, execution_id: uuid.UUID | None = None, result_id: uuid.UUID | None = None,
) -> WorkbenchOut:
    owned = await ParseItemRepository(session).get_owned(parse_id, user_id)
    if owned is None:
        raise NotFoundError("Parse item not found")
    item, _, filename = owned
    source = WorkbenchSource(
        asset_id=item.asset_id, file_name=filename, page_no=item.page_no,
        asset_content_url=f"{settings.API_PREFIX}/parse-items/{item.id}/source/content",
    )
    response = WorkbenchOut(
        parse_item=parse_item_to_out(item, filename), source=source, data_status="NO_EXECUTION",
    )
    executions = ExecutionRepository(session)
    if execution_id:
        execution = await executions.get_owned(execution_id, user_id)
        if execution is None or execution.parse_id != parse_id:
            raise NotFoundError("Execution not found")
    else:
        latest = await executions.latest_for_parse_items([parse_id])
        execution = latest.get(parse_id)
    if execution is None:
        if result_id:
            raise NotFoundError("Result not found")
        return response
    response.execution = ExecutionOut.model_validate(execution)
    results = await ResultRepository(session).list_for_execution(execution.id)
    response.results = [public_result(row) for row in results]
    selected = next((r for r in results if r.id == result_id), None) if result_id else (
        results[-1] if results else None
    )
    if result_id and selected is None:
        raise NotFoundError("Result not found in selected execution")
    if selected is None:
        response.data_status = "NO_RESULT"
        return response
    response.selected_result = public_result(selected)
    response.data_status, data = read_workbench_data(selected)
    if data is not None:
        response.artifacts = [artifact_out(selected.id, a) for a in data.artifacts]
        response.source.preview_artifact = next(
            (a for a in response.artifacts if a.id == data.source_artifact_id), None,
        )
        response.render_versions = data.render_versions
        response.verification = data.verification
        response.conversion = data.conversion
    return response


async def get_source_content(session: AsyncSession, user_id: uuid.UUID, parse_id: uuid.UUID):
    owned = await ParseItemRepository(session).get_owned(parse_id, user_id)
    if owned is None:
        raise NotFoundError("Parse item not found")
    item, _, _ = owned
    # An asset removed from the file library still backs existing task history.
    asset = await AssetRepository(session).get_by_id(item.asset_id)
    if asset is None:
        raise NotFoundError("Source not found")
    try:
        path = storage.resolve(asset.storage_key)
    except ValueError:
        raise NotFoundError("Source not found") from None
    if not path.is_file():
        raise NotFoundError("Source file not found")
    return path, asset.mime_type or "application/octet-stream", asset.file_name


async def get_artifact_content(
    session: AsyncSession, user_id: uuid.UUID, result_id: uuid.UUID, artifact_id: uuid.UUID,
):
    result = await ResultRepository(session).get_by_id(result_id)
    if result is None:
        raise NotFoundError("Artifact not found")
    execution = await ExecutionRepository(session).get_owned(result.execution_id, user_id)
    if execution is None or await ParseItemRepository(session).get_owned(execution.parse_id, user_id) is None:
        raise NotFoundError("Artifact not found")
    _, data = read_workbench_data(result)
    artifact = next((a for a in data.artifacts if a.id == artifact_id), None) if data else None
    if artifact is None:
        raise NotFoundError("Artifact not found")
    # Server-owned result prefix: never accept an arbitrary path from a URL.
    prefix = f"results/{result.execution_id}/{result.id}/"
    if not artifact.storage_key.startswith(prefix):
        raise NotFoundError("Artifact not found")
    try:
        path = storage.resolve(artifact.storage_key)
        root = storage.resolve(prefix)
    except ValueError:
        raise NotFoundError("Artifact not found") from None
    if root not in path.parents or not path.is_file():
        raise NotFoundError("Artifact file not found")
    return path, artifact.media_type
