import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.app_user import AppUser
from app.schemas.workbench import WorkbenchOut
from app.services import workbench_service

router = APIRouter(tags=["workbench"])


@router.get("/parse-items/{parse_id}/workbench", response_model=WorkbenchOut)
async def get_workbench(
    parse_id: uuid.UUID,
    execution_id: uuid.UUID | None = None,
    result_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> WorkbenchOut:
    return await workbench_service.get_workbench(
        db, user.id, parse_id, execution_id=execution_id, result_id=result_id,
    )


@router.get("/parse-items/{parse_id}/source/content")
async def source_content(
    parse_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    path, media_type, filename = await workbench_service.get_source_content(db, user.id, parse_id)
    return FileResponse(path, media_type=media_type, filename=filename,
                        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/results/{result_id}/artifacts/{artifact_id}/content")
async def artifact_content(
    result_id: uuid.UUID, artifact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    path, media_type = await workbench_service.get_artifact_content(db, user.id, result_id, artifact_id)
    return FileResponse(path, media_type=media_type,
                        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})
