import uuid

from sqlalchemy import func, select

from app.models.asset import Asset
from app.repositories.base import BaseRepository


class AssetRepository(BaseRepository[Asset]):
    model = Asset

    async def get_owned(self, asset_id: uuid.UUID, user_id: uuid.UUID) -> Asset | None:
        """Returns None both when the asset doesn't exist and when another user owns it
        (§7.6: callers must map both cases to a 404, never leaking existence)."""
        result = await self.session.execute(
            select(Asset).where(
                Asset.id == asset_id,
                Asset.user_id == user_id,
                Asset.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        page: int,
        page_size: int,
        file_type: str | None = None,
        status: str | None = None,
    ) -> tuple[list[Asset], int]:
        filters = [Asset.user_id == user_id, Asset.deleted_at.is_(None)]
        if file_type:
            filters.append(Asset.file_type == file_type)
        if status:
            filters.append(Asset.status == status)

        total_result = await self.session.execute(
            select(func.count()).select_from(Asset).where(*filters)
        )
        total = total_result.scalar_one()

        items_result = await self.session.execute(
            select(Asset)
            .where(*filters)
            .order_by(Asset.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(items_result.scalars().all()), total
