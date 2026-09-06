"""ROI 匡選 endpoints (demo step 4-6).

Collection routes hang off the owning task; single-item routes are flat, so no prefix is
set on the router itself.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.app_user import AppUser
from app.schemas.parse_item import ParseItemBulkCreate, ParseItemOut, ParseItemUpdate
from app.services import parse_item_service

router = APIRouter(tags=["parse_items"])


@router.post("/tasks/{task_id}/parse-items", response_model=list[ParseItemOut], status_code=201)
async def create_parse_items(
    task_id: uuid.UUID,
    body: ParseItemBulkCreate,
    db: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> list[ParseItemOut]:
    return await parse_item_service.create_parse_items(db, user.id, task_id, body)


@router.get("/tasks/{task_id}/parse-items", response_model=list[ParseItemOut])
async def list_parse_items(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> list[ParseItemOut]:
    return await parse_item_service.list_parse_items(db, user.id, task_id)


@router.get("/parse-items/{parse_item_id}", response_model=ParseItemOut)
async def get_parse_item(
    parse_item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> ParseItemOut:
    return await parse_item_service.get_parse_item(db, user.id, parse_item_id)


@router.patch("/parse-items/{parse_item_id}", response_model=ParseItemOut)
async def update_parse_item(
    parse_item_id: uuid.UUID,
    body: ParseItemUpdate,
    db: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> ParseItemOut:
    return await parse_item_service.update_parse_item(db, user.id, parse_item_id, body)


@router.delete("/parse-items/{parse_item_id}", status_code=204)
async def delete_parse_item(
    parse_item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> None:
    await parse_item_service.delete_parse_item(db, user.id, parse_item_id)
