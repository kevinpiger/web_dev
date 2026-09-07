import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.model_flow import ModelFlow
from app.repositories.model_flow_repository import ModelFlowRepository
from app.schemas.model_flow import ModelFlowCreate, ModelFlowOut


async def list_flows(db: AsyncSession) -> list[ModelFlowOut]:
    return [ModelFlowOut.model_validate(flow) for flow in await ModelFlowRepository(db).list_active()]


async def create_flow(db: AsyncSession, body: ModelFlowCreate) -> ModelFlowOut:
    flow = ModelFlow(**body.model_dump())
    db.add(flow)
    await db.flush()
    output = ModelFlowOut.model_validate(flow)
    await db.commit()
    return output


async def delete_flow(db: AsyncSession, flow_id: uuid.UUID) -> None:
    if not await ModelFlowRepository(db).soft_delete(flow_id):
        raise NotFoundError("Model flow not found")
    await db.commit()
