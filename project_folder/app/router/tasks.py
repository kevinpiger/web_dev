import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.app_user import AppUser
from app.schemas.task import TaskCreate, TaskDetail, TaskListResponse, TaskOut, TaskUpdate
from app.services import task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", response_model=TaskOut, status_code=201)
async def create_task(
    body: TaskCreate,
    db: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> TaskOut:
    return await task_service.create_task(db, user.id, body)


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    db: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> TaskListResponse:
    return TaskListResponse(items=await task_service.list_tasks(db, user.id))


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> TaskOut:
    return await task_service.get_task(db, user.id, task_id)


@router.get("/{task_id}/detail", response_model=TaskDetail)
async def get_task_detail(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> TaskDetail:
    """主任務底下的所有子任務：ROI、最新一次執行、目前的最終解析程式。"""
    return await task_service.get_task_detail(db, user.id, task_id)


@router.patch("/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: uuid.UUID,
    body: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> TaskOut:
    return await task_service.update_task(db, user.id, task_id, body)


@router.post("/{task_id}/cancel", response_model=TaskOut)
async def cancel_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> TaskOut:
    return await task_service.cancel_task(db, user.id, task_id)


@router.delete("/{task_id}", status_code=204)
async def delete_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> None:
    await task_service.delete_task(db, user.id, task_id)
