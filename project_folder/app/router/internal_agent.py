"""Sandbox endpoints are independent of the user API prefix and authentication."""
import uuid

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_auth import AgentIdentity, require_agent, require_worker
from app.core.deps import get_db
from app.core.exceptions import NotFoundError
from app.schemas.agent import (
    AgentContext, ArtifactReceipt, AttemptCreate, AttemptGrant, AttemptState,
    FailureReceipt, FailureSubmission, ResultReceipt, ResultSubmission, WorkerState,
)
from app.services import agent_service as service
from app.utils import storage


async def no_cache(response: Response):
    response.headers["Cache-Control"] = "no-store"


worker_router = APIRouter(prefix="/internal/worker", tags=["Internal Worker"],
                         dependencies=[Depends(require_worker), Depends(no_cache)])
agent_router = APIRouter(prefix="/internal/agent", tags=["Sandbox Agent"],
                        dependencies=[Depends(no_cache)])


@worker_router.post("/executions/{execution_id}/attempts", response_model=AttemptGrant,
                    summary="原子領取 execution 並簽發單次沙盒憑證")
async def create_attempt(execution_id: uuid.UUID, payload: AttemptCreate,
                         db: AsyncSession = Depends(get_db)):
    return await service.claim(db, execution_id, payload.attempt_id)


@worker_router.get("/executions/{execution_id}", response_model=WorkerState,
                   summary="查詢 execution、回收逾期租約與取得重試資格")
async def get_worker_execution(execution_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await service.worker_state(db, execution_id)


@agent_router.get("/context", response_model=AgentContext, summary="讀取本次解析輸入")
async def get_context(identity: AgentIdentity = Depends(require_agent), db: AsyncSession = Depends(get_db)):
    return await service.context(db, identity)


@agent_router.get("/source", response_class=FileResponse, summary="下載本次 execution 的來源檔案")
async def get_source(identity: AgentIdentity = Depends(require_agent), db: AsyncSession = Depends(get_db)):
    values = await service.agent_scope(db, identity)
    service.ensure_current(values)
    asset = await service.source_asset(db, values)
    path = storage.resolve(asset.storage_key)
    if not path.is_file():
        raise NotFoundError("Source file is unavailable")
    file_name, media_type = asset.file_name, asset.mime_type or "application/octet-stream"
    # Release row locks before streaming. Cancellation cannot revoke bytes already sent.
    await db.rollback()
    return FileResponse(path, filename=file_name, media_type=media_type,
                        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@agent_router.post("/heartbeat", response_model=AttemptState, summary="續租或取得停止原因")
async def heartbeat(identity: AgentIdentity = Depends(require_agent), db: AsyncSession = Depends(get_db)):
    return await service.heartbeat(db, identity)


@agent_router.post("/artifacts", response_model=ArtifactReceipt, summary="上傳不可覆寫的成果圖片")
async def upload_artifact(result_id: uuid.UUID = Form(...), artifact_id: uuid.UUID = Form(...),
                          file: UploadFile = File(...), identity: AgentIdentity = Depends(require_agent),
                          db: AsyncSession = Depends(get_db)):
    return await service.upload_artifact(db, identity, result_id, artifact_id, file)


@agent_router.post("/results", response_model=ResultReceipt, summary="保存中間解析版本")
async def create_result(payload: ResultSubmission, identity: AgentIdentity = Depends(require_agent),
                        db: AsyncSession = Depends(get_db)):
    return await service.submit_result(db, identity, payload)


@agent_router.post("/complete", response_model=ResultReceipt, summary="原子提交最終結果並完成 execution")
async def complete(payload: ResultSubmission, identity: AgentIdentity = Depends(require_agent),
                   db: AsyncSession = Depends(get_db)):
    return await service.submit_result(db, identity, payload, complete=True)


@agent_router.post("/fail", response_model=FailureReceipt, summary="回報失敗或逾時與重試提示")
async def fail(payload: FailureSubmission, identity: AgentIdentity = Depends(require_agent),
               db: AsyncSession = Depends(get_db)):
    return await service.fail(db, identity, payload)
