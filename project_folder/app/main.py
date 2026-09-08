import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.exceptions import register_exception_handlers
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
