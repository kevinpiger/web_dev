"""Separate trust domains for worker orchestration and one sandbox attempt."""
import secrets
import uuid
from dataclasses import dataclass

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import settings
from app.core.exceptions import AppError, UnauthorizedError

ISSUER = "datasheet-backend"
AUDIENCE = "sandbox-agent"
_bearer = HTTPBearer(auto_error=False)


class AgentConfigurationError(AppError):
    status_code = 503
    error_code = "AGENT_API_NOT_CONFIGURED"


def require_configuration():
    keys = (settings.WORKER_API_KEY, settings.AGENT_JWT_SECRET)
    if any(len(k) < 32 for k in keys) or len(set((*keys, settings.JWT_SECRET_KEY))) != 3:
        raise AgentConfigurationError("Configure distinct worker and agent secrets of at least 32 characters")


async def require_worker(x_worker_key: str | None = Header(default=None)):
    require_configuration()
    if x_worker_key is None or not secrets.compare_digest(x_worker_key.encode("utf-8"), settings.WORKER_API_KEY.encode("utf-8")):
        raise UnauthorizedError("Invalid worker credential")


@dataclass(frozen=True)
class AgentIdentity:
    execution_id: uuid.UUID
    attempt_id: uuid.UUID
    token_id: uuid.UUID


def issue_token(attempt) -> str:
    require_configuration()
    return jwt.encode({
        "iss": ISSUER, "aud": AUDIENCE, "type": "agent_attempt",
        "sub": str(attempt.execution_id), "attempt_id": str(attempt.id),
        "jti": str(attempt.token_id), "iat": int(attempt.started_at.timestamp()),
        "exp": int(attempt.token_expires_at.timestamp()),
    }, settings.AGENT_JWT_SECRET, algorithm="HS256")


async def require_agent(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> AgentIdentity:
    require_configuration()
    if credentials is None:
        raise UnauthorizedError("Agent credential required")
    try:
        payload = jwt.decode(credentials.credentials, settings.AGENT_JWT_SECRET,
                             algorithms=["HS256"], audience=AUDIENCE, issuer=ISSUER,
                             options={"require_exp": True, "require_iat": True,
                                      "require_sub": True, "require_jti": True,
                                      "require_aud": True, "require_iss": True})
        if payload.get("type") != "agent_attempt":
            raise ValueError("Wrong token type")
        return AgentIdentity(uuid.UUID(payload["sub"]), uuid.UUID(payload["attempt_id"]),
                             uuid.UUID(payload["jti"]))
    except (JWTError, KeyError, ValueError, TypeError, AttributeError):
        raise UnauthorizedError("Invalid or expired agent credential") from None
