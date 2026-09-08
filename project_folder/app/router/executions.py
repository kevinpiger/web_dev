"""送出任務 / 執行狀態 / 中斷單筆執行 (demo step 7)."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.app_user import AppUser
from app.models.result import Result
from app.schemas.result import ExecutionResultCreate, ResultOut
from app.schemas.common import Page
from app.schemas.execution import CancelResult, DispatchResult, ExecutionOut
from app.services import execution_service

router = APIRouter(tags=["executions"])


@router.post("/tasks/{task_id}/dispatch", response_model=DispatchResult, status_code=202)
async def dispatch_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> DispatchResult:
    """建立 execution 與 outbox event，交棒給 queue。本階段不直接接 RabbitMQ。"""
    return await execution_service.dispatch_task(db, user.id, task_id)


@router.get("/executions", response_model=Page[ExecutionOut])
async def list_executions(
    db: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    task_id: uuid.UUID | None = None,
    parse_id: uuid.UUID | None = None,
    status: str | None = None,
) -> Page[ExecutionOut]:
    items, total = await execution_service.list_executions(
        db,
        user.id,
        page=page,
        page_size=page_size,
        task_id=task_id,
        parse_id=parse_id,
        status=status,
    )
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/executions/{execution_id}", response_model=ExecutionOut)
async def get_execution(
    execution_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> ExecutionOut:
    return await execution_service.get_execution(db, user.id, execution_id)


@router.post("/executions/{execution_id}/cancel", response_model=CancelResult)
async def cancel_execution(
    execution_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> CancelResult:
    return await execution_service.cancel_execution(db, user.id, execution_id)


@router.post("/executions/{execution_id}/results", response_model=ResultOut,
             status_code=201, summary="免 Token 測試：寫入解析結果")
async def create_execution_result(
    execution_id: uuid.UUID,
    body: ExecutionResultCreate,
    db: AsyncSession = Depends(get_db),
) -> Result:
    return await execution_service.append_test_result(db, execution_id, body)
