from fastapi import APIRouter

from app.router import assets, auth, executions, parse_items, results, tasks, users, workbench

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(assets.router)
api_router.include_router(users.router)
api_router.include_router(tasks.router)
api_router.include_router(parse_items.router)
api_router.include_router(executions.router)
api_router.include_router(results.router)

api_router.include_router(workbench.router)
