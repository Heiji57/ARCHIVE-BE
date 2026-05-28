from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from dishka import make_async_container
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.auth.presentation.router import router as auth_router
from app.shared.domain.exceptions.base import BaseAppException
from app.shared.infrastructure.config.settings import get_settings
from app.shared.infrastructure.container.providers import AppProvider, RequestProvider


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    container = make_async_container(AppProvider(), RequestProvider())
    setup_dishka(container, app=app)
    yield
    await container.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="ARCHIVE API",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
    )

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

    app.include_router(auth_router, prefix="/api/v1")
    return app


app = create_app()
