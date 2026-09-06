import uuid

from fastapi import APIRouter, Depends, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.app_user import AppUser
from app.schemas.asset import AssetOut, AssetUploadResponse
from app.schemas.common import Page
from app.services import asset_service
from app.utils import storage

router = APIRouter(prefix="/assets", tags=["assets"])


@router.post("", response_model=AssetUploadResponse)
async def upload_assets(
    files: list[UploadFile],
    db: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> AssetUploadResponse:
    return await asset_service.upload_assets(db, user.id, files)


@router.get("", response_model=Page[AssetOut])
async def list_assets(
    db: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    file_type: str | None = None,
    status: str | None = None,
) -> Page[AssetOut]:
    items, total = await asset_service.list_assets(
        db, user.id, page=page, page_size=page_size, file_type=file_type, status=status
    )
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/{asset_id}", response_model=AssetOut)
async def get_asset(
    asset_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> AssetOut:
    return await asset_service.get_asset(db, user.id, asset_id)


@router.get("/{asset_id}/content")
async def download_asset(
    asset_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> StreamingResponse:
    asset = await asset_service.get_asset_for_download(db, user.id, asset_id)

    def _iter_file():
        file_obj = storage.open_file(asset.storage_key)
        try:
            while chunk := file_obj.read(storage.CHUNK_SIZE):
                yield chunk
        finally:
            file_obj.close()

    return StreamingResponse(
        _iter_file(),
        media_type=asset.mime_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{asset.file_name}"'},
    )


@router.delete("/{asset_id}", status_code=204)
async def delete_asset(
    asset_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> None:
    await asset_service.delete_asset(db, user.id, asset_id)
