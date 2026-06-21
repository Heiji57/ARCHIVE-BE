from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from dishka import make_async_container
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.auth.presentation.router import router as auth_router
from app.github.presentation.router import router as github_router
from app.notification.presentation.router import router as notification_router
from app.settings.presentation.router import router as settings_router
from app.retrospective.presentation.router import router as entry_router
from app.retrospective.presentation.summary_router import router as summary_router
from app.retrospective.presentation.retro_template_router import router as retro_template_router
from app.retrospective.presentation.template_router import (
    active_router as summary_active_router,
    template_router as summary_template_router,
)
from app.shared.domain.exceptions.base import BaseAppException
from app.todo.presentation.router import router as todo_router
from app.shared.infrastructure.config.settings import get_settings
from app.shared.infrastructure.container.providers import AppProvider, RequestProvider


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    yield
    # dishka 가 만든 APP-scope 인스턴스 중 명시적으로 close 가 필요한 것들 정리.
    # GitHubApiClient 는 httpx.AsyncClient 를 멤버로 유지하므로 lifespan 종료 시 닫는다.
    try:
        from app.github.infrastructure.api.github_api_client import GitHubApiClient
        api_client: GitHubApiClient = await app.state.dishka_container.get(GitHubApiClient)
        await api_client.close()
    except Exception:
        pass
    # dishka가 app.state.dishka_container에 컨테이너를 저장함
    await app.state.dishka_container.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="ARCHIVE API",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
    )

    # setup_dishka는 앱 시작 전(create_app 단계)에 호출해야 미들웨어 등록 가능
    container = make_async_container(AppProvider(), RequestProvider())
    setup_dishka(container, app=app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(BaseAppException)
    async def app_exception_handler(request: Request, exc: BaseAppException) -> JSONResponse:
        from app.shared.infrastructure.errors.handler import to_http_response
        return to_http_response(exc)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        from app.shared.infrastructure.errors.handler import validation_exception_handler as _handler
        return await _handler(request, exc)

    app.mount("/static", StaticFiles(directory="static"), name="static")

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(todo_router, prefix="/api/v1")
    app.include_router(entry_router, prefix="/api/v1")
    app.include_router(summary_router, prefix="/api/v1")
    app.include_router(summary_template_router, prefix="/api/v1")
    app.include_router(summary_active_router, prefix="/api/v1")
    app.include_router(retro_template_router, prefix="/api/v1")
    app.include_router(notification_router, prefix="/api/v1")
    app.include_router(settings_router, prefix="/api/v1")
    app.include_router(github_router, prefix="/api/v1")
    return app


app = create_app()
