import uuid
from collections.abc import AsyncGenerator

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import JWTError, TOKEN_TYPE_ACCESS, decode_token
from app.db.session import get_session
from app.models.app_user import AppUser
from app.repositories.app_user_repository import AppUserRepository

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_session():
        yield session


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> AppUser:
    if credentials is None:
        raise UnauthorizedError("Not authenticated")

    try:
        payload = decode_token(credentials.credentials)
    except JWTError as exc:
        raise UnauthorizedError("Invalid or expired token") from exc

    if payload.get("type") != TOKEN_TYPE_ACCESS:
        raise UnauthorizedError("Invalid or expired token")

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise UnauthorizedError("Invalid or expired token") from exc

    user = await AppUserRepository(db).get_active_by_id(user_id)
    if user is None:
        raise UnauthorizedError("Invalid or expired token")

    return user


def require_role(*allowed_role_codes: str):
    async def _dependency(
        user: AppUser = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> AppUser:
        from sqlalchemy import select

        from app.models.role import Role

        result = await db.execute(select(Role.code).where(Role.id == user.role_id))
        role_code = result.scalar_one()
        if role_code not in allowed_role_codes:
            raise ForbiddenError("Insufficient permissions")
        return user

    return _dependency
