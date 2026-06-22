from datetime import datetime, timedelta, timezone

from fastapi import Cookie, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.auth.domain.exceptions.exceptions import (
    AuthTokenExpiredException,
    AuthTokenInvalidException,
    RefreshTokenInvalidException,
)
from app.auth.domain.models.value_objects import TokenType
from app.shared.domain.context.user_context import UserContext
from app.shared.infrastructure.config.settings import get_settings

_ALGORITHM = "HS256"
_bearer = HTTPBearer(auto_error=False)


def _create_token(
    user_id: str, token_type: TokenType, expires_delta: timedelta, account_type: str = "user"
) -> str:
    settings = get_settings()
    payload = {
        "sub": user_id,
        "type": token_type,
        "account_type": account_type,
        "exp": datetime.now(timezone.utc) + expires_delta,
    }
    return jwt.encode(payload, settings.auth.secret_key, algorithm=_ALGORITHM)


def create_access_token(user_id: str, account_type: str = "user") -> str:
    settings = get_settings()
    return _create_token(
        user_id,
        TokenType.ACCESS,
        timedelta(minutes=settings.auth.access_token_expire_minutes),
        account_type=account_type,
    )


def _decode(token: str, expected_type: TokenType) -> UserContext:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.auth.secret_key, algorithms=[_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise AuthTokenExpiredException()
    except JWTError:
        raise AuthTokenInvalidException()

    if payload.get("type") != expected_type:
        raise AuthTokenInvalidException()

    return UserContext(
        id=payload["sub"],
        email=payload.get("email", ""),
        account_type=payload.get("account_type", "user"),
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> UserContext:
    if not credentials:
        raise AuthTokenInvalidException()
    return _decode(credentials.credentials, TokenType.ACCESS)


def extract_refresh_token(refresh_token: str | None = Cookie(default=None, alias="refresh_token")) -> str:
    if not refresh_token:
        raise RefreshTokenInvalidException()
    return refresh_token
