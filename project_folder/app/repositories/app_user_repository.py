import uuid

from sqlalchemy import select

from app.models.app_user import AppUser
from app.repositories.base import BaseRepository


class AppUserRepository(BaseRepository[AppUser]):
    model = AppUser

    async def get_by_email(self, email: str) -> AppUser | None:
        result = await self.session.execute(select(AppUser).where(AppUser.email == email))
        return result.scalar_one_or_none()

    async def get_active_by_id(self, user_id: uuid.UUID) -> AppUser | None:
        result = await self.session.execute(
            select(AppUser).where(AppUser.id == user_id, AppUser.is_active.is_(True))
        )
        return result.scalar_one_or_none()
