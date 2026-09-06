import uuid
from datetime import datetime

from pydantic import BaseModel


class AssetOut(BaseModel):
    id: uuid.UUID
    file_name: str
    file_type: str
    mime_type: str | None
    file_size: int | None
    status: str
    attributes: dict
    created_at: datetime

    model_config = {"from_attributes": True}


class AssetUploadError(BaseModel):
    file_name: str
    error_code: str
    message: str


class AssetUploadResponse(BaseModel):
    succeeded: list[AssetOut]
    failed: list[AssetUploadError]
