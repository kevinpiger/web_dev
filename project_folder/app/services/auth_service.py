"""Business logic for login / refresh / logout / me. Router only handles HTTP concerns."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnauthorizedError
from app.core.security import (
    JWTError,
    TOKEN_TYPE_REFRESH,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_refresh_token,
    verify_password,
)
from app.models.app_user import AppUser
from app.models.role import Role
from app.repositories.app_user_repository import AppUserRepository
from app.schemas.auth import TokenResponse, UserOut
from app.utils.datetime import utcnow

_GENERIC_LOGIN_ERROR = "Invalid email or password"


async def _role_code_for(session: AsyncSession, user: AppUser) -> str:
    result = await session.execute(select(Role.code).where(Role.id == user.role_id))
    return result.scalar_one()


async def _issue_token_response(session: AsyncSession, user: AppUser) -> TokenResponse:
    role_code = await _role_code_for(session, user)

    access_token, expires_in = create_access_token(user_id=str(user.id), role=role_code)
    refresh_token, refresh_expire_at = create_refresh_token(user_id=str(user.id), role=role_code)

    user.token = hash_refresh_token(refresh_token)
    user.token_expire_at = refresh_expire_at
    await session.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        user=UserOut(
            id=user.id,
            username=user.username,
            email=user.email,
            employee_no=user.employee_no,
            organization=user.organization,
            role=role_code,
        ),
    )


async def login(session: AsyncSession, *, email: str, password: str) -> TokenResponse:
    repo = AppUserRepository(session)
    user = await repo.get_by_email(email)

    # §6: account-not-found / wrong-password / inactive must all fail identically.
    if user is None or not user.is_active or not user.password_hash:
        raise UnauthorizedError(_GENERIC_LOGIN_ERROR)

    if not verify_password(password, user.password_hash):
        raise UnauthorizedError(_GENERIC_LOGIN_ERROR)

    user.last_login_at = utcnow()
    return await _issue_token_response(session, user)


async def refresh(session: AsyncSession, *, refresh_token: str) -> TokenResponse:
    try:
        payload = decode_token(refresh_token)
    except JWTError as exc:
        raise UnauthorizedError("Invalid or expired refresh token") from exc

    if payload.get("type") != TOKEN_TYPE_REFRESH:
        raise UnauthorizedError("Invalid or expired refresh token")

    repo = AppUserRepository(session)
    user = await repo.get_by_id(uuid.UUID(payload["sub"]))
    if user is None or not user.is_active:
        raise UnauthorizedError("Invalid or expired refresh token")

    if user.token != hash_refresh_token(refresh_token):
        raise UnauthorizedError("Invalid or expired refresh token")

    # Rotate: issuing a new refresh token immediately invalidates this one.
    return await _issue_token_response(session, user)


async def logout(session: AsyncSession, *, refresh_token: str) -> None:
    try:
        payload = decode_token(refresh_token)
        user = await AppUserRepository(session).get_by_id(uuid.UUID(payload["sub"]))
    except (JWTError, KeyError, ValueError):
        user = None

    if user is not None:
        user.token = None
        user.token_expire_at = None
        await session.commit()


async def get_me(session: AsyncSession, user: AppUser) -> UserOut:
    role_code = await _role_code_for(session, user)
    return UserOut(
        id=user.id,
        username=user.username,
        email=user.email,
        employee_no=user.employee_no,
        organization=user.organization,
        role=role_code,
    )
