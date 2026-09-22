from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from dishka import make_async_container
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from redis.exceptions import RedisError

from app.auth.presentation.router import router as auth_router
from app.auth.presentation.router_v2 import router as auth_router_v2
from app.github.presentation.router import router as github_router
from app.google_calendar.presentation.router import router as calendar_router
from app.notification.presentation.router import router as notification_router
from app.retrospective.presentation.folder_router import router as folder_router
from app.retrospective.presentation.retro_template_router import router as retro_template_router
from app.retrospective.presentation.router import router as entry_router
from app.retrospective.presentation.summary_router import router as summary_router
from app.retrospective.presentation.template_router import (
    active_router as summary_active_router,
)
from app.retrospective.presentation.template_router import (
    template_router as summary_template_router,
)
from app.search.presentation.router import router as search_router
from app.settings.presentation.router import router as settings_router
from app.shared.domain.exceptions.base import BaseAppException
from app.shared.domain.exceptions.external import CacheUnavailableException
from app.shared.infrastructure.config.settings import get_settings
from app.shared.infrastructure.container.providers import AppProvider, RequestProvider
from app.shared.infrastructure.logger.request_context import (
    REQUEST_ID_HEADER,
    RequestContextMiddleware,
)
from app.shared.infrastructure.logger.setup import configure_logging
from app.todo.presentation.router import router as todo_router
from app.topic.presentation.router import router as topic_router

_log = structlog.get_logger(__name__)


async def _close_app_client(app: FastAPI, client_type: type) -> None:
    """APP-scope httpx 클라이언트 종료. 종료 경계라 하나가 실패해도 나머지 정리는 계속한다."""
    try:
        client = await app.state.dishka_container.get(client_type)
        await client.close()
    except Exception:
        _log.error("lifespan.client_close_failed", client=client_type.__name__, exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    yield
    # dishka 가 만든 APP-scope 인스턴스 중 명시적으로 close 가 필요한 것들 정리 —
    # 둘 다 httpx.AsyncClient 를 멤버로 유지한다.
    from app.github.infrastructure.api.github_api_client import GitHubApiClient
    from app.google_calendar.infrastructure.api.google_calendar_client import (
        GoogleCalendarApiClient,
    )

    await _close_app_client(app, GitHubApiClient)
    await _close_app_client(app, GoogleCalendarApiClient)
    # dishka가 app.state.dishka_container에 컨테이너를 저장함
    await app.state.dishka_container.close()


def create_app() -> FastAPI:
    configure_logging()
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

    # 순서 주의 — add_middleware 는 바깥쪽에 쌓는다. RequestContext 를 먼저 추가해 CORS 보다
    # 안쪽에 둬야, 처리되지 않은 예외로 여기서 만든 500 응답에도 CORS 헤더가 붙는다.
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[REQUEST_ID_HEADER],  # FE 가 문의·버그 리포트에 request id 를 실을 수 있게
    )

    @app.exception_handler(BaseAppException)
    async def app_exception_handler(request: Request, exc: BaseAppException) -> JSONResponse:
        from app.shared.infrastructure.errors.handler import (
            api_version_of,
            log_error_response,
            to_http_response,
        )
        response = to_http_response(exc, api_version_of(request.url.path))
        log_error_response(exc, response.status_code)
        return response

    @app.exception_handler(RedisError)
    async def redis_exception_handler(request: Request, exc: RedisError) -> JSONResponse:
        # 캐시 클래스가 10여 개라 각각 감싸는 대신 경계 한 곳에서 번역한다. 로그인 제한·refresh
        # token·OAuth state 가 전부 Redis 라 fail-closed(503) — 우회 허용보다 거부가 안전.
        from app.shared.infrastructure.errors.handler import (
            api_version_of,
            log_error_response,
            to_http_response,
        )
        translated = CacheUnavailableException(f"{type(exc).__name__}: {exc}")
        translated.__cause__ = exc
        response = to_http_response(translated, api_version_of(request.url.path))
        log_error_response(translated, response.status_code)
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        from app.shared.infrastructure.errors.handler import (
            validation_exception_handler as _handler,
        )
        return await _handler(request, exc)

    app.mount("/static", StaticFiles(directory="static"), name="static")

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(todo_router, prefix="/api/v1")
    app.include_router(entry_router, prefix="/api/v1")
    app.include_router(folder_router, prefix="/api/v1")
    # /summaries/templates 가 /summaries/{summary_id} 로 가로채이지 않도록
    # template 라우터를 summary 라우터보다 먼저 등록한다.
    app.include_router(summary_template_router, prefix="/api/v1")
    app.include_router(summary_active_router, prefix="/api/v1")
    app.include_router(summary_router, prefix="/api/v1")
    app.include_router(retro_template_router, prefix="/api/v1")
    app.include_router(notification_router, prefix="/api/v1")
    app.include_router(settings_router, prefix="/api/v1")
    app.include_router(github_router, prefix="/api/v1")
    app.include_router(calendar_router, prefix="/api/v1")
    app.include_router(search_router, prefix="/api/v1")
    app.include_router(topic_router, prefix="/api/v1")
    # v2 — 에러 코드가 세분화된 일부 엔드포인트만 (나머지는 v1 유지)
    app.include_router(auth_router_v2, prefix="/api/v2")
    return app


app = create_app()
