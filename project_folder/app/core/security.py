"""JWT issue/decode, password hashing, refresh-token hashing."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"


def hash_password(plain_password: str) -> str:
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return _pwd_context.verify(plain_password, password_hash)


def _create_token(*, subject: str, role: str, token_type: str, expires_delta: timedelta) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(*, user_id: str, role: str) -> tuple[str, int]:
    expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    token = _create_token(
        subject=user_id, role=role, token_type=TOKEN_TYPE_ACCESS, expires_delta=expires_delta
    )
    return token, int(expires_delta.total_seconds())


def create_refresh_token(*, user_id: str, role: str) -> tuple[str, datetime]:
    expires_delta = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    token = _create_token(
        subject=user_id, role=role, token_type=TOKEN_TYPE_REFRESH, expires_delta=expires_delta
    )
    return token, datetime.now(UTC) + expires_delta


def decode_token(token: str) -> dict[str, Any]:
    """Raises jose.JWTError on invalid/expired token; callers decide how to map that."""
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


def hash_refresh_token(token: str) -> str:
    """Refresh tokens are stored hashed in app_user.token, never in plaintext."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_opaque_token() -> str:
    return secrets.token_urlsafe(32)


__all__ = [
    "JWTError",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "generate_opaque_token",
    "hash_password",
    "hash_refresh_token",
    "verify_password",
]
