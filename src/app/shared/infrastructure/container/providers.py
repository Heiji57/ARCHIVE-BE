from collections.abc import AsyncGenerator

from dishka import Provider, Scope, provide
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.application.use_cases.get_me import GetMeUseCase
from app.auth.application.use_cases.handle_oauth_callback import HandleOAuthCallbackUseCase
from app.auth.application.use_cases.initiate_oauth import InitiateOAuthUseCase
from app.auth.application.use_cases.login import LoginUseCase
from app.auth.application.use_cases.logout import LogoutUseCase
from app.auth.application.use_cases.refresh_token import RefreshTokenUseCase
from app.auth.application.use_cases.register import RegisterUseCase
from app.auth.application.use_cases.send_email_verification import SendEmailVerificationUseCase
from app.auth.application.use_cases.update_profile import UpdateProfileUseCase
from app.auth.application.use_cases.verify_email_code import VerifyEmailCodeUseCase
from app.auth.domain.models.value_objects import OAuthProvider
from app.auth.domain.repositories.repository import IOAuthConnectionRepository
from app.auth.infrastructure.cache.auth_token import AuthTokenCache
from app.auth.infrastructure.cache.email_verification import EmailVerificationCache
from app.auth.infrastructure.cache.oauth_state import OAuthStateCache
from app.auth.infrastructure.oauth.github_client import GitHubOAuthClient
from app.auth.infrastructure.oauth.google_client import GoogleOAuthClient
from app.auth.infrastructure.oauth.registry import OAuthClientRegistry
from app.auth.infrastructure.persistence.repositories.oauth_connection_repo import OAuthConnectionRepository
from app.github.application.use_cases.link_repository import LinkRepositoryUseCase
from app.github.application.use_cases.list_available_repositories import ListAvailableRepositoriesUseCase
from app.github.application.use_cases.list_linked_repositories import ListLinkedRepositoriesUseCase
from app.github.application.use_cases.sync_all_repositories import SyncAllRepositoriesUseCase
from app.github.application.use_cases.unlink_all_repositories import UnlinkAllRepositoriesUseCase
from app.github.application.use_cases.unlink_repository import UnlinkRepositoryUseCase
from app.github.domain.repositories.repository import IGitHubRepositoryRepository
from app.github.infrastructure.api.github_api_client import GitHubApiClient
from app.github.infrastructure.persistence.repositories.github_repository_repo import GitHubRepositoryRepository
from app.notification.application.use_cases.create_notification import CreateNotificationUseCase
from app.settings.application.use_cases.get_settings import GetSettingsUseCase
from app.settings.application.use_cases.update_settings import UpdateSettingsUseCase
from app.settings.domain.repositories.repository import IUserSettingsRepository
from app.settings.infrastructure.persistence.repositories.user_settings_repo import UserSettingsRepository
from app.notification.application.use_cases.delete_notification import DeleteNotificationUseCase
from app.notification.application.use_cases.delete_notifications import DeleteNotificationsUseCase
from app.notification.application.use_cases.get_notifications import GetNotificationsUseCase
from app.notification.application.use_cases.mark_all_as_read import MarkAllAsReadUseCase
from app.notification.application.use_cases.mark_as_read import MarkAsReadUseCase
from app.notification.domain.repositories.repository import INotificationRepository
from app.notification.infrastructure.persistence.repositories.notification_repo import NotificationRepository
from app.retrospective.application.use_cases.create_entry import CreateEntryUseCase
from app.retrospective.application.use_cases.delete_entry import DeleteEntryUseCase
from app.retrospective.application.use_cases.get_entries import GetEntriesUseCase
from app.retrospective.application.use_cases.get_entry import GetEntryUseCase
from app.retrospective.application.use_cases.get_summaries import GetSummariesUseCase
from app.retrospective.application.use_cases.get_summary import GetSummaryUseCase
from app.retrospective.application.use_cases.request_summary import RequestSummaryUseCase
from app.retrospective.application.use_cases.upsert_entry import UpsertEntryUseCase
from app.retrospective.domain.repositories.repository import IJournalEntryRepository, IRetroSummaryRepository
from app.retrospective.infrastructure.persistence.repositories.journal_entry_repo import JournalEntryRepository
from app.retrospective.infrastructure.persistence.repositories.retro_summary_repo import RetroSummaryRepository
from app.shared.infrastructure.config.settings import AppConfig, get_settings
from app.todo.application.use_cases.create_todo import CreateTodoUseCase
from app.todo.application.use_cases.delete_todo import DeleteTodoUseCase
from app.todo.application.use_cases.get_todos_by_date import GetTodosByDateUseCase
from app.todo.application.use_cases.get_todos_by_range import GetTodosByRangeUseCase
from app.todo.application.use_cases.update_todo import UpdateTodoUseCase
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

    @provide
    def oauth_state_cache(self, config: AppConfig) -> OAuthStateCache:
        redis = Redis.from_url(config.redis.cache_url, decode_responses=True)
        return OAuthStateCache(redis)

    @provide
    def oauth_client_registry(self, config: AppConfig) -> OAuthClientRegistry:
        return OAuthClientRegistry({
            OAuthProvider.GITHUB: GitHubOAuthClient(config.github_oauth),
            OAuthProvider.GOOGLE: GoogleOAuthClient(config.google_oauth),
        })

    @provide
    def github_api_client(self) -> GitHubApiClient:
        return GitHubApiClient()


class RequestProvider(Provider):
    """REQUEST scope — 요청마다 생성·소멸하는 의존성."""

    scope = Scope.REQUEST

    @provide
    async def db_session(
        self, factory: async_sessionmaker[AsyncSession]
    ) -> AsyncGenerator[AsyncSession, None]:
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

    @provide
    def user_settings_repo(self, session: AsyncSession) -> IUserSettingsRepository:
        return UserSettingsRepository(session)

    @provide
    def oauth_connection_repo(self, session: AsyncSession) -> IOAuthConnectionRepository:
        return OAuthConnectionRepository(session)

    @provide
    def github_repository_repo(self, session: AsyncSession) -> IGitHubRepositoryRepository:
        return GitHubRepositoryRepository(session)

    # ── Notification Use Cases ────────────────────────────────────────────────

    @provide
    def create_notification_use_case(
        self, repo: INotificationRepository
    ) -> CreateNotificationUseCase:
        return CreateNotificationUseCase(repo)

    @provide
    def get_notifications_use_case(
        self, repo: INotificationRepository
    ) -> GetNotificationsUseCase:
        return GetNotificationsUseCase(repo)

    @provide
    def mark_as_read_use_case(self, repo: INotificationRepository) -> MarkAsReadUseCase:
        return MarkAsReadUseCase(repo)

    @provide
    def mark_all_as_read_use_case(self, repo: INotificationRepository) -> MarkAllAsReadUseCase:
        return MarkAllAsReadUseCase(repo)

    @provide
    def delete_notification_use_case(
        self, repo: INotificationRepository
    ) -> DeleteNotificationUseCase:
        return DeleteNotificationUseCase(repo)

    @provide
    def delete_notifications_use_case(
        self, repo: INotificationRepository
    ) -> DeleteNotificationsUseCase:
        return DeleteNotificationsUseCase(repo)

    # ── Settings Use Cases ────────────────────────────────────────────────────

    @provide
    def get_settings_use_case(self, repo: IUserSettingsRepository) -> GetSettingsUseCase:
        return GetSettingsUseCase(repo)

    @provide
    def update_settings_use_case(self, repo: IUserSettingsRepository) -> UpdateSettingsUseCase:
        return UpdateSettingsUseCase(repo)

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

    @provide
    def initiate_oauth_use_case(
        self, registry: OAuthClientRegistry, state_cache: OAuthStateCache
    ) -> InitiateOAuthUseCase:
        return InitiateOAuthUseCase(registry, state_cache)

    @provide
    def handle_oauth_callback_use_case(
        self,
        registry: OAuthClientRegistry,
        state_cache: OAuthStateCache,
        oauth_connection_repo: IOAuthConnectionRepository,
        user_repo: IUserRepository,
        auth_token_cache: AuthTokenCache,
    ) -> HandleOAuthCallbackUseCase:
        return HandleOAuthCallbackUseCase(
            registry, state_cache, oauth_connection_repo, user_repo, auth_token_cache
        )

    # ── Todo Use Cases ────────────────────────────────────────────────────────

    @provide
    def create_todo_use_case(self, todo_repo: ITodoRepository) -> CreateTodoUseCase:
        return CreateTodoUseCase(todo_repo)

    @provide
    def update_todo_use_case(self, todo_repo: ITodoRepository) -> UpdateTodoUseCase:
        return UpdateTodoUseCase(todo_repo)

    @provide
    def delete_todo_use_case(self, todo_repo: ITodoRepository) -> DeleteTodoUseCase:
        return DeleteTodoUseCase(todo_repo)

    @provide
    def get_todos_by_date_use_case(self, todo_repo: ITodoRepository) -> GetTodosByDateUseCase:
        return GetTodosByDateUseCase(todo_repo)

    @provide
    def get_todos_by_range_use_case(self, todo_repo: ITodoRepository) -> GetTodosByRangeUseCase:
        return GetTodosByRangeUseCase(todo_repo)

    # ── Journal Entry Use Cases ───────────────────────────────────────────────

    @provide
    def create_entry_use_case(
        self, entry_repo: IJournalEntryRepository
    ) -> CreateEntryUseCase:
        return CreateEntryUseCase(entry_repo)

    @provide
    def upsert_entry_use_case(
        self, entry_repo: IJournalEntryRepository
    ) -> UpsertEntryUseCase:
        return UpsertEntryUseCase(entry_repo)

    @provide
    def get_entry_use_case(
        self, entry_repo: IJournalEntryRepository
    ) -> GetEntryUseCase:
        return GetEntryUseCase(entry_repo)

    @provide
    def get_entries_use_case(
        self, entry_repo: IJournalEntryRepository
    ) -> GetEntriesUseCase:
        return GetEntriesUseCase(entry_repo)

    @provide
    def delete_entry_use_case(
        self, entry_repo: IJournalEntryRepository
    ) -> DeleteEntryUseCase:
        return DeleteEntryUseCase(entry_repo)

    # ── Summary Use Cases ─────────────────────────────────────────────────────

    @provide
    def request_summary_use_case(
        self, summary_repo: IRetroSummaryRepository
    ) -> RequestSummaryUseCase:
        return RequestSummaryUseCase(summary_repo)

    @provide
    def get_summary_use_case(
        self, summary_repo: IRetroSummaryRepository
    ) -> GetSummaryUseCase:
        return GetSummaryUseCase(summary_repo)

    @provide
    def get_summaries_use_case(
        self, summary_repo: IRetroSummaryRepository
    ) -> GetSummariesUseCase:
        return GetSummariesUseCase(summary_repo)

    # ── GitHub Use Cases ──────────────────────────────────────────────────────

    @provide
    def list_available_repositories_use_case(
        self,
        oauth_repo: IOAuthConnectionRepository,
        api_client: GitHubApiClient,
    ) -> ListAvailableRepositoriesUseCase:
        return ListAvailableRepositoriesUseCase(oauth_repo, api_client)

    @provide
    def list_linked_repositories_use_case(
        self, repo: IGitHubRepositoryRepository
    ) -> ListLinkedRepositoriesUseCase:
        return ListLinkedRepositoriesUseCase(repo)

    @provide
    def link_repository_use_case(
        self,
        repo: IGitHubRepositoryRepository,
        oauth_repo: IOAuthConnectionRepository,
        api_client: GitHubApiClient,
    ) -> LinkRepositoryUseCase:
        return LinkRepositoryUseCase(repo, oauth_repo, api_client)

    @provide
    def sync_all_repositories_use_case(
        self,
        repo: IGitHubRepositoryRepository,
        oauth_repo: IOAuthConnectionRepository,
        api_client: GitHubApiClient,
    ) -> SyncAllRepositoriesUseCase:
        return SyncAllRepositoriesUseCase(repo, oauth_repo, api_client)

    @provide
    def unlink_repository_use_case(
        self, repo: IGitHubRepositoryRepository
    ) -> UnlinkRepositoryUseCase:
        return UnlinkRepositoryUseCase(repo)

    @provide
    def unlink_all_repositories_use_case(
        self, repo: IGitHubRepositoryRepository
    ) -> UnlinkAllRepositoriesUseCase:
        return UnlinkAllRepositoriesUseCase(repo)
