from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.auth.infrastructure.cache.auth_token import AuthTokenCache
from app.auth.infrastructure.cache.email_verification import EmailVerificationCache
from app.auth.application.use_cases.login import LoginUseCase
from app.auth.application.use_cases.register import RegisterUseCase
from app.auth.application.use_cases.send_email_verification import SendEmailVerificationUseCase
from app.auth.application.use_cases.verify_email_code import VerifyEmailCodeUseCase
from app.auth.presentation.router import router as auth_router
from app.shared.domain.exceptions.base import BaseAppException
from app.shared.infrastructure.cache.redis import build_auth_client, build_cache_client
from app.shared.infrastructure.config.settings import get_settings
from app.shared.infrastructure.database.session import build_session_factory
from app.user.infrastructure.persistence.repositories.user_repo import UserRepository


class _Container:
    """요청마다 생성되는 간단한 DI 컨테이너 (dishka 연동 전 임시)."""

    def __init__(self, request: Request) -> None:
        session_factory = request.app.state.session_factory
        auth_redis = request.app.state.auth_redis
        cache_redis = request.app.state.cache_redis

        auth_config = request.app.state.auth_config
        self._session = session_factory()
        user_repo = UserRepository(self._session)
        verification_cache = EmailVerificationCache(cache_redis, auth_config)
        auth_token_cache = AuthTokenCache(auth_redis, auth_config)

        self.send_email_verification = SendEmailVerificationUseCase(verification_cache)
        self.verify_email_code = VerifyEmailCodeUseCase(verification_cache)
        self.register = RegisterUseCase(user_repo, verification_cache, auth_token_cache)
        self.login = LoginUseCase(user_repo, auth_token_cache)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    app.state.auth_config = settings.auth
    app.state.session_factory = build_session_factory()
    app.state.auth_redis = build_auth_client()
    app.state.cache_redis = build_cache_client()
    yield
    await app.state.auth_redis.aclose()
    await app.state.cache_redis.aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="ARCHIVE API",
        lifespan=lifespan,
        docs_url="/docs" if settings.is_development else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def inject_container(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.container = _Container(request)
        return await call_next(request)

    @app.exception_handler(BaseAppException)
    async def app_exception_handler(request: Request, exc: BaseAppException) -> JSONResponse:
        from app.shared.infrastructure.errors.handler import to_http_response
        return to_http_response(exc)

    app.include_router(auth_router, prefix="/api/v1")
    return app


app = create_app()
