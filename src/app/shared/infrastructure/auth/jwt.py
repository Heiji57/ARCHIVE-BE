from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.auth.domain.exceptions.exceptions import (
    AuthTokenExpiredException,
    AuthTokenInvalidException,
)
from app.auth.domain.models.value_objects import TokenType
from app.shared.domain.context.user_context import UserContext
from app.shared.infrastructure.config.settings import get_settings

_ALGORITHM = "HS256"


def _create_token(user_id: str, token_type: TokenType, expires_delta: timedelta) -> str:
    settings = get_settings()
    payload = {
        "sub": user_id,
        "type": token_type,
        "exp": datetime.now(timezone.utc) + expires_delta,
    }
    return jwt.encode(payload, settings.auth.secret_key, algorithm=_ALGORITHM)


def create_access_token(user_id: str) -> str:
    settings = get_settings()
    return _create_token(
        user_id,
        TokenType.ACCESS,
        timedelta(minutes=settings.auth.access_token_expire_minutes),
    )


def create_pre_auth_token(user_id: str) -> str:
    settings = get_settings()
    return _create_token(
        user_id,
        TokenType.PRE_AUTH,
        timedelta(minutes=settings.auth.pre_auth_token_expire_minutes),
    )


def decode_token(token: str, expected_type: TokenType) -> UserContext:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.auth.secret_key, algorithms=[_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise AuthTokenExpiredException()
    except JWTError:
        raise AuthTokenInvalidException()

    if payload.get("type") != expected_type:
        raise AuthTokenInvalidException()

    return UserContext(id=payload["sub"], email=payload.get("email", ""))


def get_current_user(token: str) -> UserContext:
    return decode_token(token, TokenType.ACCESS)


def get_pre_auth_user(token: str) -> UserContext:
    return decode_token(token, TokenType.PRE_AUTH)
