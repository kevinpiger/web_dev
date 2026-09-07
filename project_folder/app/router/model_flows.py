import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.schemas.model_flow import ModelFlowCreate, ModelFlowListResponse, ModelFlowOut
from app.services import model_flow_service

router = APIRouter(
    prefix="/model-flows", tags=["model-flows"], dependencies=[Depends(get_current_user)]
)


@router.get("", response_model=ModelFlowListResponse)
async def list_model_flows(db: AsyncSession = Depends(get_db)) -> ModelFlowListResponse:
    return ModelFlowListResponse(items=await model_flow_service.list_flows(db))


@router.post("", response_model=ModelFlowOut, status_code=201)
async def create_model_flow(
    body: ModelFlowCreate, db: AsyncSession = Depends(get_db)
) -> ModelFlowOut:
    return await model_flow_service.create_flow(db, body)


@router.delete("/{flow_id}", status_code=204)
async def delete_model_flow(flow_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Response:
    await model_flow_service.delete_flow(db, flow_id)
    return Response(status_code=204)
