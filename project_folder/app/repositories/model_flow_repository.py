import uuid

from sqlalchemy import select, update

from app.models.model_flow import ModelFlow
from app.repositories.base import BaseRepository
from app.utils.datetime import utcnow


class ModelFlowRepository(BaseRepository[ModelFlow]):
    model = ModelFlow

    async def list_active(self) -> list[ModelFlow]:
        result = await self.session.execute(
            select(ModelFlow)
            .where(ModelFlow.deleted_at.is_(None))
            .order_by(ModelFlow.created_at.desc(), ModelFlow.id.desc())
        )
        return list(result.scalars().all())

    async def soft_delete(self, flow_id: uuid.UUID) -> bool:
        now = utcnow()
        result = await self.session.execute(
            update(ModelFlow)
            .where(ModelFlow.id == flow_id, ModelFlow.deleted_at.is_(None))
            .values(deleted_at=now, updated_at=now, is_valid=False)
            .returning(ModelFlow.id)
        )
        return result.scalar_one_or_none() is not None
