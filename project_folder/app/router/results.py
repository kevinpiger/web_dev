"""最終解析程式：版本歷史與「編輯後存成最新一版」(append-only)."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.app_user import AppUser
from app.schemas.result import ResultAppend, ResultOut
from app.services import result_service

router = APIRouter(tags=["results"])


@router.get("/parse-items/{parse_item_id}/results", response_model=list[ResultOut])
async def list_results(
    parse_item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> list[ResultOut]:
    """版本演進：該子任務最新一次執行的每一輪結果，由舊到新。"""
    return await result_service.list_results(db, user.id, parse_item_id)


@router.post("/parse-items/{parse_item_id}/results", response_model=ResultOut, status_code=201)
async def append_result(
    parse_item_id: uuid.UUID,
    body: ResultAppend,
    db: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> ResultOut:
    """存檔即 append 一筆新的 round，不覆蓋既有版本。"""
    return await result_service.append_result(db, user.id, parse_item_id, body)
