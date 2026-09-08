import logging
import uuid
from typing import Any
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import get_db
from app.core.exceptions import NotFoundError, register_exception_handlers
from app.models.execution import Execution
from app.models.result import Result
from app.repositories.result_repository import ResultRepository
from app.schemas.result import ResultOut
from app.core.logging import configure_logging
from app.db import bootstrap
from app.router import api_router
from app.router.health import router as health_router
from app.router.internal_agent import agent_router, worker_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging()
    Path(settings.STORAGE_PATH).mkdir(parents=True, exist_ok=True)

    if settings.DB_AUTO_BOOTSTRAP:
        await bootstrap.run()
    else:
        logger.info("DB_AUTO_BOOTSTRAP=false, skipping schema bootstrap")

    yield


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(health_router)
app.include_router(api_router, prefix=settings.API_PREFIX)

# Internal credentials are deliberately independent of user access tokens.
app.include_router(worker_router)
app.include_router(agent_router)


class TestResultCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_id: uuid.UUID
    result_info: dict[str, Any]


@app.post("/results", response_model=ResultOut, status_code=201,
          tags=["Test Results"], summary="免 Token 測試：寫入解析結果")
async def create_test_result(
    body: TestResultCreate, db: AsyncSession = Depends(get_db),
) -> Result:
    """Append a raw result snapshot without changing the execution lifecycle."""
    execution = (await db.execute(
        select(Execution).where(Execution.id == body.execution_id).with_for_update()
    )).scalar_one_or_none()
    if execution is None:
        raise NotFoundError("Execution not found")

    result = Result(
        execution_id=execution.id,
        round_no=await ResultRepository(db).next_round_no(execution.id),
        status="SUCCEEDED",
        result_info=body.result_info,
    )
    db.add(result)
    await db.commit()
    await db.refresh(result)
    return result
