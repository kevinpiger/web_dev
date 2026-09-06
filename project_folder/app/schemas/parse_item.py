import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ParseItemCreate(BaseModel):
    """One ROI. Demo modes map onto this shape:

    - 整張解析  -> omit x/y/width/height (defaults cover the whole page)
    - 選擇區域  -> send normalized x/y/width/height
    - 不解析此頁 -> send nothing for that page
    """

    asset_id: uuid.UUID
    page_no: int = Field(default=1, ge=1)
    name: str | None = Field(default=None, max_length=255)
    x: float = 0.0
    y: float = 0.0
    width: float = 1.0
    height: float = 1.0


class ParseItemBulkCreate(BaseModel):
    items: list[ParseItemCreate] = Field(min_length=1)


class ParseItemUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    status: str | None = None
    page_no: int | None = Field(default=None, ge=1)
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None


class ParseItemOut(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    asset_id: uuid.UUID
    asset_file_name: str
    name: str | None
    status: str
    page_no: int
    x: float
    y: float
    width: float
    height: float
    created_at: datetime
