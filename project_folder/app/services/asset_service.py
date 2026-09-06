"""Business logic for asset upload / list / detail / download / delete (spec §7)."""

import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.enums import AssetFileType, AssetStatus, StorageType
from app.core.exceptions import NotFoundError
from app.models.asset import Asset
from app.repositories.asset_repository import AssetRepository
from app.schemas.asset import AssetOut, AssetUploadError, AssetUploadResponse
from app.utils import storage
from app.utils.datetime import utcnow
from app.utils.pdf import page_count

_EXTENSION_TO_FILE_TYPE = {
    "pdf": AssetFileType.PDF,
    "png": AssetFileType.IMAGE,
    "jpg": AssetFileType.IMAGE,
    "jpeg": AssetFileType.IMAGE,
    "svg": AssetFileType.SVG,
}


def _extension_of(filename: str) -> str:
    return Path(filename).suffix.lstrip(".").lower()


def _map_file_type(extension: str) -> AssetFileType:
    return _EXTENSION_TO_FILE_TYPE.get(extension, AssetFileType.OTHER)


async def _upload_one(
    session: AsyncSession, user_id: uuid.UUID, upload_file: UploadFile
) -> AssetOut | AssetUploadError:
    file_name = upload_file.filename or "unnamed"
    extension = _extension_of(file_name)

    if extension not in settings.allowed_upload_extensions_set:
        return AssetUploadError(
            file_name=file_name,
            error_code="UNSUPPORTED_EXTENSION",
            message="不支援的副檔名",
        )

    repo = AssetRepository(session)
    safe_name = storage.sanitize_filename(file_name)
    asset = Asset(
        user_id=user_id,
        file_name=file_name,
        mime_type=upload_file.content_type,
        file_type=_map_file_type(extension).value,
        storage_type=StorageType.LOCAL.value,
        storage_key="",
        file_size=None,
        attributes={},
        status=AssetStatus.UPLOADING.value,
    )
    repo.add(asset)
    await repo.flush()

    rel_path = f"assets/{user_id}/{asset.id}/{safe_name}"
    asset.storage_key = rel_path

    try:
        bytes_written = await storage.save_stream(rel_path, upload_file)
    except OSError:
        asset.status = AssetStatus.FAILED.value
        await session.commit()
        storage.delete(rel_path)
        return AssetUploadError(
            file_name=file_name,
            error_code="UPLOAD_FAILED",
            message="檔案寫入失敗",
        )

    if bytes_written > settings.max_upload_size_bytes:
        storage.delete(rel_path)
        asset.status = AssetStatus.FAILED.value
        await session.commit()
        return AssetUploadError(
            file_name=file_name,
            error_code="FILE_TOO_LARGE",
            message=f"檔案超過 {settings.MAX_UPLOAD_SIZE_MB}MB",
        )

    attributes: dict = {}
    if asset.file_type == AssetFileType.PDF.value:
        try:
            attributes["page_count"] = page_count(storage.resolve(rel_path))
        except Exception:  # noqa: BLE001 - a corrupt PDF still counts as a successful upload
            attributes["page_count"] = None

    asset.file_size = bytes_written
    asset.attributes = attributes
    asset.status = AssetStatus.READY.value
    await session.commit()

    return AssetOut.model_validate(asset)


async def upload_assets(
    session: AsyncSession, user_id: uuid.UUID, files: list[UploadFile]
) -> AssetUploadResponse:
    succeeded: list[AssetOut] = []
    failed: list[AssetUploadError] = []

    for upload_file in files:
        outcome = await _upload_one(session, user_id, upload_file)
        if isinstance(outcome, AssetUploadError):
            failed.append(outcome)
        else:
            succeeded.append(outcome)

    return AssetUploadResponse(succeeded=succeeded, failed=failed)


async def list_assets(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    page: int,
    page_size: int,
    file_type: str | None,
    status: str | None,
) -> tuple[list[AssetOut], int]:
    repo = AssetRepository(session)
    assets, total = await repo.list_for_user(
        user_id, page=page, page_size=page_size, file_type=file_type, status=status
    )
    return [AssetOut.model_validate(asset) for asset in assets], total


async def get_asset(session: AsyncSession, user_id: uuid.UUID, asset_id: uuid.UUID) -> AssetOut:
    asset = await AssetRepository(session).get_owned(asset_id, user_id)
    if asset is None:
        raise NotFoundError("Asset not found")
    return AssetOut.model_validate(asset)


async def get_asset_for_download(
    session: AsyncSession, user_id: uuid.UUID, asset_id: uuid.UUID
) -> Asset:
    asset = await AssetRepository(session).get_owned(asset_id, user_id)
    if asset is None:
        raise NotFoundError("Asset not found")
    return asset


async def delete_asset(session: AsyncSession, user_id: uuid.UUID, asset_id: uuid.UUID) -> None:
    asset = await AssetRepository(session).get_owned(asset_id, user_id)
    if asset is None:
        # Repeated deletes are idempotent, but a never-existing/foreign asset stays a 404.
        exists_for_other_user = await session.get(Asset, asset_id)
        if exists_for_other_user is None or exists_for_other_user.user_id != user_id:
            raise NotFoundError("Asset not found")
        return  # already soft-deleted -> idempotent 204

    asset.deleted_at = utcnow()
    await session.commit()
