import time
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from fastapi import Cookie, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from redis.asyncio import Redis
from redis.exceptions import RedisError

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
    user_id: str,
    token_type: TokenType,
    expires_delta: timedelta,
    extra: dict[str, Any] | None = None,
) -> str:
    settings = get_settings()
    payload: dict[str, Any] = {
        "sub": user_id,
        "type": token_type,
        "exp": datetime.now(timezone.utc) + expires_delta,
        **(extra or {}),
    }
    token: str = jwt.encode(payload, settings.auth.secret_key, algorithm=_ALGORITHM)
    return token


def create_access_token(user_id: str, auth_time: float | None = None) -> str:
    """auth_time = 자격 증명을 확인한 시각(epoch 초). 로그인·가입·OAuth 는 지금(기본값),
    refresh 는 세션의 발급 시각을 넘겨 "최근 로그인" 판단이 refresh 로 갱신되지 않게 한다."""
    settings = get_settings()
    return _create_token(
        user_id,
        TokenType.ACCESS,
        timedelta(minutes=settings.auth.access_token_expire_minutes),
        {"auth_time": int(auth_time if auth_time is not None else time.time())},
    )


def _decode(token: str, expected_type: TokenType) -> UserContext:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.auth.secret_key, algorithms=[_ALGORITHM])
    except jwt.ExpiredSignatureError as e:
        raise AuthTokenExpiredException() from e
    except JWTError as e:
        raise AuthTokenInvalidException() from e

    if payload.get("type") != expected_type:
        raise AuthTokenInvalidException()
    # 서명이 유효해도 sub 가 없으면 사용자를 특정할 수 없다 — KeyError(500) 대신 401.
    user_id = payload.get("sub")
    if not isinstance(user_id, str) or not user_id:
        raise AuthTokenInvalidException()

    auth_time = payload.get("auth_time")
    return UserContext(
        id=user_id,
        email=payload.get("email", ""),
        auth_time=float(auth_time) if isinstance(auth_time, int | float) else None,
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> UserContext:
    if not credentials:
        raise AuthTokenInvalidException()
    user = _decode(credentials.credentials, TokenType.ACCESS)
    if await is_account_deleted(user.id):
        # 지운 계정의 남은 access token — 만료(최대 15분)까지 기다리지 않고 바로 막는다.
        raise AuthTokenInvalidException()
    # 이후 이 요청의 모든 로그 줄에 user_id 가 붙는다 (request_context 미들웨어가 요청마다 초기화).
    structlog.contextvars.bind_contextvars(user_id=user.id)
    return user


# ── 지운 계정의 남은 access token 막기 ───────────────────────────────────────
# get_current_user 는 DB 를 읽지 않으므로, 계정 삭제 때 Redis 에 표식을 access token 수명만큼 둔다.
DELETED_USER_KEY = "deleted_user:{user_id}"
_redis: Redis | None = None


def _deleted_marker_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(get_settings().redis.auth_url, decode_responses=True)
    return _redis


async def is_account_deleted(user_id: str) -> bool:
    try:
        return bool(await _deleted_marker_redis().exists(DELETED_USER_KEY.format(user_id=user_id)))
    except RedisError:
        # Redis 장애로 모든 요청을 401 로 만들지 않는다 — 지운 계정은 세션이 이미 없어
        # 남은 access token 수명(최대 15분)이 상한이다.
        structlog.get_logger(__name__).warning("auth.deleted_marker_unavailable", exc_info=True)
        return False


def extract_refresh_token(refresh_token: str | None = Cookie(default=None, alias="refresh_token")) -> str:
    if not refresh_token:
        raise RefreshTokenInvalidException()
    return refresh_token


# ── 주간 이메일 수신 거부 링크 ────────────────────────────────────────────────
# 로그인 없이 메일의 링크만으로 email_digest 를 끈다. 다른 토큰과 섞이지 않게 type 을 따로 둔다.
_UNSUBSCRIBE_TOKEN_TYPE = "email_unsubscribe"
_UNSUBSCRIBE_TOKEN_DAYS = 60


def create_unsubscribe_token(user_id: str) -> str:
    settings = get_settings()
    payload = {
        "sub": user_id,
        "type": _UNSUBSCRIBE_TOKEN_TYPE,
        "exp": datetime.now(timezone.utc) + timedelta(days=_UNSUBSCRIBE_TOKEN_DAYS),  # noqa: UP017
    }
    token: str = jwt.encode(payload, settings.auth.secret_key, algorithm=_ALGORITHM)
    return token


def decode_unsubscribe_token(token: str) -> str:
    """유효하면 user_id. 만료·위조·다른 종류 토큰이면 AuthTokenInvalidException."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.auth.secret_key, algorithms=[_ALGORITHM])
    except JWTError as e:
        raise AuthTokenInvalidException() from e
    user_id = payload.get("sub")
    if payload.get("type") != _UNSUBSCRIBE_TOKEN_TYPE or not isinstance(user_id, str):
        raise AuthTokenInvalidException()
    return user_id


# ── 내보내기 내려받기 서명 URL ────────────────────────────────────────────────
_EXPORT_TOKEN_TYPE = "export_download"


def create_export_download_token(export_id: str, expires: timedelta) -> str:
    settings = get_settings()
    payload = {
        "sub": export_id,
        "type": _EXPORT_TOKEN_TYPE,
        "exp": datetime.now(timezone.utc) + expires,  # noqa: UP017
    }
    token: str = jwt.encode(payload, settings.auth.secret_key, algorithm=_ALGORITHM)
    return token


def decode_export_download_token(token: str) -> str:
    """유효하면 export id. 만료·위조·다른 종류 토큰이면 AuthTokenInvalidException."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.auth.secret_key, algorithms=[_ALGORITHM])
    except JWTError as e:
        raise AuthTokenInvalidException() from e
    export_id = payload.get("sub")
    if payload.get("type") != _EXPORT_TOKEN_TYPE or not isinstance(export_id, str):
        raise AuthTokenInvalidException()
    return export_id
