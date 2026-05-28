from collections.abc import AsyncGenerator

from dishka import Provider, Scope, provide
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.application.use_cases.login import LoginUseCase
from app.auth.application.use_cases.logout import LogoutUseCase
from app.auth.application.use_cases.refresh_token import RefreshTokenUseCase
from app.auth.application.use_cases.register import RegisterUseCase
from app.auth.application.use_cases.send_email_verification import SendEmailVerificationUseCase
from app.auth.application.use_cases.verify_email_code import VerifyEmailCodeUseCase
from app.auth.application.use_cases.get_me import GetMeUseCase
from app.auth.application.use_cases.update_profile import UpdateProfileUseCase
from app.auth.infrastructure.cache.auth_token import AuthTokenCache
from app.auth.infrastructure.cache.email_verification import EmailVerificationCache
from app.notification.domain.repositories.repository import INotificationRepository
from app.notification.infrastructure.persistence.repositories.notification_repo import NotificationRepository
from app.retrospective.domain.repositories.repository import IJournalEntryRepository, IRetroSummaryRepository
from app.retrospective.infrastructure.persistence.repositories.journal_entry_repo import JournalEntryRepository
from app.retrospective.infrastructure.persistence.repositories.retro_summary_repo import RetroSummaryRepository
from app.shared.infrastructure.config.settings import AppConfig, get_settings
from app.todo.domain.repositories.repository import ITodoRepository
from app.todo.infrastructure.persistence.repositories.todo_repo import TodoRepository
from app.user.domain.repositories.repository import IUserRepository
from app.user.infrastructure.persistence.repositories.user_repo import UserRepository


class AppProvider(Provider):
    """APP scope — 앱 전체에서 싱글턴으로 유지되는 의존성."""

    scope = Scope.APP

    @provide
    def settings(self) -> AppConfig:
        return get_settings()

    @provide
    def session_factory(self, config: AppConfig) -> async_sessionmaker[AsyncSession]:
        engine = create_async_engine(
            config.db.url,
            pool_size=config.db.pool_size,
            max_overflow=config.db.max_overflow,
            pool_timeout=config.db.pool_timeout,
            echo=config.is_development,
        )
        return async_sessionmaker(engine, expire_on_commit=False)

    @provide
    def auth_token_cache(self, config: AppConfig) -> AuthTokenCache:
        redis = Redis.from_url(config.redis.auth_url, decode_responses=True)
        return AuthTokenCache(redis, config.auth)

    @provide
    def email_verification_cache(self, config: AppConfig) -> EmailVerificationCache:
        redis = Redis.from_url(config.redis.cache_url, decode_responses=True)
        return EmailVerificationCache(redis, config.auth)


class RequestProvider(Provider):
    """REQUEST scope — 요청마다 생성·소멸하는 의존성."""

    scope = Scope.REQUEST

    @provide
    async def db_session(
        self, factory: async_sessionmaker[AsyncSession]
    ) -> AsyncGenerator[AsyncSession, None]:
        # begin() = 성공 시 자동 커밋, 예외 시 자동 롤백
        async with factory.begin() as session:
            yield session

    # ── Repositories ──────────────────────────────────────────────────────────

    @provide
    def user_repo(self, session: AsyncSession) -> IUserRepository:
        return UserRepository(session)

    @provide
    def todo_repo(self, session: AsyncSession) -> ITodoRepository:
        return TodoRepository(session)

    @provide
    def journal_entry_repo(self, session: AsyncSession) -> IJournalEntryRepository:
        return JournalEntryRepository(session)

    @provide
    def retro_summary_repo(self, session: AsyncSession) -> IRetroSummaryRepository:
        return RetroSummaryRepository(session)

    @provide
    def notification_repo(self, session: AsyncSession) -> INotificationRepository:
        return NotificationRepository(session)

    # ── Auth Use Cases ────────────────────────────────────────────────────────

    @provide
    def send_email_verification_use_case(
        self, cache: EmailVerificationCache
    ) -> SendEmailVerificationUseCase:
        return SendEmailVerificationUseCase(cache)

    @provide
    def verify_email_code_use_case(
        self, cache: EmailVerificationCache
    ) -> VerifyEmailCodeUseCase:
        return VerifyEmailCodeUseCase(cache)

    @provide
    def register_use_case(
        self,
        user_repo: IUserRepository,
        verification_cache: EmailVerificationCache,
        auth_token_cache: AuthTokenCache,
    ) -> RegisterUseCase:
        return RegisterUseCase(user_repo, verification_cache, auth_token_cache)

    @provide
    def login_use_case(
        self,
        user_repo: IUserRepository,
        auth_token_cache: AuthTokenCache,
    ) -> LoginUseCase:
        return LoginUseCase(user_repo, auth_token_cache)

    @provide
    def refresh_token_use_case(
        self,
        user_repo: IUserRepository,
        auth_token_cache: AuthTokenCache,
    ) -> RefreshTokenUseCase:
        return RefreshTokenUseCase(user_repo, auth_token_cache)

    @provide
    def logout_use_case(self, auth_token_cache: AuthTokenCache) -> LogoutUseCase:
        return LogoutUseCase(auth_token_cache)

    @provide
    def get_me_use_case(self, user_repo: IUserRepository) -> GetMeUseCase:
        return GetMeUseCase(user_repo)

    @provide
    def update_profile_use_case(self, user_repo: IUserRepository) -> UpdateProfileUseCase:
        return UpdateProfileUseCase(user_repo)
