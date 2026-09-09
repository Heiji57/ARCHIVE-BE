from collections.abc import AsyncGenerator

from dishka import Provider, Scope, provide
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.application.services.session_service import SessionService
from app.auth.application.use_cases.complete_onboarding import CompleteOnboardingUseCase
from app.auth.application.use_cases.get_me import GetMeUseCase
from app.auth.application.use_cases.handle_oauth_callback import HandleOAuthCallbackUseCase
from app.auth.application.use_cases.initiate_oauth import InitiateOAuthUseCase
from app.auth.application.use_cases.initiate_oauth_link import InitiateOAuthLinkUseCase
from app.auth.application.use_cases.list_sessions import ListSessionsUseCase
from app.auth.application.use_cases.login import LoginUseCase
from app.auth.application.use_cases.logout import LogoutUseCase
from app.auth.application.use_cases.refresh_token import RefreshTokenUseCase
from app.auth.application.use_cases.register import RegisterUseCase
from app.auth.application.use_cases.request_password_reset import RequestPasswordResetUseCase
from app.auth.application.use_cases.reset_password import ResetPasswordUseCase
from app.auth.application.use_cases.revoke_session import (
    RevokeOtherSessionsUseCase,
    RevokeSessionUseCase,
)
from app.auth.application.use_cases.send_email_verification import SendEmailVerificationUseCase
from app.auth.application.use_cases.update_profile import UpdateProfileUseCase
from app.auth.application.use_cases.verify_email_code import VerifyEmailCodeUseCase
from app.auth.domain.models.value_objects import OAuthProvider
from app.auth.domain.repositories.repository import IOAuthConnectionRepository
from app.auth.infrastructure.cache.auth_token import AuthTokenCache
from app.auth.infrastructure.cache.email_verification import EmailVerificationCache
from app.auth.infrastructure.cache.login_attempt import LoginAttemptCache
from app.auth.infrastructure.cache.oauth_state import OAuthStateCache
from app.auth.infrastructure.cache.onboarding import OnboardingTokenCache
from app.auth.infrastructure.cache.password_reset import PasswordResetCache
from app.auth.infrastructure.oauth.github_client import GitHubOAuthClient
from app.auth.infrastructure.oauth.google_client import GoogleOAuthClient
from app.auth.infrastructure.oauth.registry import OAuthClientRegistry
from app.auth.infrastructure.persistence.repositories.oauth_connection_repo import OAuthConnectionRepository
from app.github.application.use_cases.get_commits_by_date import GetCommitsByDateUseCase
from app.github.application.use_cases.get_connection_status import GetConnectionStatusUseCase
from app.github.application.use_cases.link_repository import LinkRepositoryUseCase
from app.github.application.use_cases.list_available_repositories import ListAvailableRepositoriesUseCase
from app.github.application.use_cases.list_linked_repositories import ListLinkedRepositoriesUseCase
from app.github.application.use_cases.push_retrospective import PushRetrospectiveUseCase
from app.github.application.use_cases.sync_all_repositories import SyncAllRepositoriesUseCase
from app.github.application.use_cases.unlink_all_repositories import UnlinkAllRepositoriesUseCase
from app.github.application.use_cases.unlink_repository import UnlinkRepositoryUseCase
from app.github.application.use_cases.update_repository import UpdateRepositoryUseCase
from app.github.domain.repositories.repository import IGitHubRepositoryRepository
from app.github.domain.repositories.retrospective_push_repository import (
    IRetrospectivePushRepository,
)
from app.github.infrastructure.api.github_api_client import GitHubApiClient
from app.github.infrastructure.persistence.repositories.github_repository_repo import GitHubRepositoryRepository
from app.github.infrastructure.persistence.repositories.retrospective_push_repo import (
    RetrospectivePushRepository,
)
from app.google_calendar.application.use_cases.disconnect_calendar import (
    DisconnectCalendarUseCase,
)
from app.google_calendar.application.use_cases.get_calendar_events import (
    GetCalendarEventsUseCase,
)
from app.google_calendar.application.use_cases.get_connection_status import (
    GetCalendarConnectionStatusUseCase,
)
from app.google_calendar.application.use_cases.handle_calendar_callback import (
    HandleCalendarCallbackUseCase,
)
from app.google_calendar.application.use_cases.initiate_calendar_connect import (
    InitiateCalendarConnectUseCase,
)
from app.google_calendar.application.use_cases.sync_calendar_events import (
    SyncCalendarEventsUseCase,
)
from app.google_calendar.domain.repositories.repository import (
    ICalendarEventRepository,
    IGoogleCalendarConnectionRepository,
)
from app.google_calendar.infrastructure.api.google_calendar_client import (
    GoogleCalendarApiClient,
)
from app.google_calendar.infrastructure.cache.calendar_state import (
    CalendarOAuthStateCache,
)
from app.google_calendar.infrastructure.persistence.repositories.calendar_connection_repo import (
    GoogleCalendarConnectionRepository,
)
from app.google_calendar.infrastructure.persistence.repositories.calendar_event_repo import (
    CalendarEventRepository,
)
from app.notification.application.use_cases.create_notification import CreateNotificationUseCase
from app.settings.application.use_cases.get_settings import GetSettingsUseCase
from app.settings.application.use_cases.list_country_timezones import (
    ListCountryTimezonesUseCase,
)
from app.settings.application.use_cases.update_country import UpdateCountryUseCase
from app.settings.application.use_cases.update_settings import UpdateSettingsUseCase
from app.settings.application.use_cases.update_timezone import UpdateTimezoneUseCase
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
from app.retrospective.application.use_cases.create_folder import CreateFolderUseCase
from app.retrospective.application.use_cases.delete_entry import DeleteEntryUseCase
from app.retrospective.application.use_cases.delete_folder import DeleteFolderUseCase
from app.retrospective.application.use_cases.get_entries import GetEntriesUseCase
from app.retrospective.application.use_cases.get_entries_page import GetEntriesPageUseCase
from app.retrospective.application.use_cases.get_folder_contents import GetFolderContentsUseCase
from app.retrospective.application.use_cases.list_folders import ListFoldersUseCase
from app.retrospective.application.use_cases.move_entry_to_folder import MoveEntryToFolderUseCase
from app.retrospective.application.use_cases.update_folder import UpdateFolderUseCase
from app.search.application.use_cases.global_search import GlobalSearchUseCase
from app.retrospective.application.use_cases.get_entry import GetEntryUseCase
from app.retrospective.application.use_cases.edit_summary import EditSummaryUseCase
from app.retrospective.application.use_cases.get_summaries import GetSummariesUseCase
from app.retrospective.application.use_cases.get_summary import GetSummaryUseCase
from app.retrospective.application.use_cases.get_summary_readiness import (
    GetSummaryReadinessUseCase,
)
from app.retrospective.application.use_cases.create_retro_template import CreateRetroTemplateUseCase
from app.retrospective.application.use_cases.delete_retro_template import DeleteRetroTemplateUseCase
from app.retrospective.application.use_cases.list_retro_templates import ListRetroTemplatesUseCase
from app.retrospective.application.use_cases.reset_retro_template import ResetRetroTemplateUseCase
from app.retrospective.application.use_cases.seed_retro_templates import SeedRetroTemplatesUseCase
from app.retrospective.application.use_cases.set_active_retro_template import SetActiveRetroTemplateUseCase
from app.retrospective.application.use_cases.update_retro_template import UpdateRetroTemplateUseCase
from app.retrospective.application.use_cases.create_summary_template import (
    CreateSummaryTemplateUseCase,
)
from app.retrospective.application.use_cases.delete_summary_template import (
    DeleteSummaryTemplateUseCase,
)
from app.retrospective.application.use_cases.get_summary_template import (
    GetSummaryTemplateUseCase,
)
from app.retrospective.application.use_cases.get_summary_usage import (
    GetSummaryUsageUseCase,
)
from app.retrospective.application.use_cases.list_summary_templates import (
    ListSummaryTemplatesUseCase,
)
from app.retrospective.application.use_cases.request_summary import RequestSummaryUseCase
from app.retrospective.application.use_cases.set_active_summary_template import (
    SetActiveSummaryTemplateUseCase,
)
from app.retrospective.application.use_cases.update_summary_template import (
    UpdateSummaryTemplateUseCase,
)
from app.retrospective.application.use_cases.upsert_entry import UpsertEntryUseCase
from app.retrospective.domain.repositories.repository import (
    IFolderRepository,
    IJournalEntryRepository,
    IRetroSummaryRepository,
    IRetroTemplateRepository,
    IUserSummaryTemplateRepository,
)
from app.retrospective.infrastructure.persistence.repositories.retro_template_repo import RetroTemplateRepository
from app.retrospective.infrastructure.cache.summary_rate_limiter import SummaryRateLimiter
from app.retrospective.infrastructure.persistence.repositories.folder_repo import FolderRepository
from app.retrospective.infrastructure.persistence.repositories.journal_entry_repo import JournalEntryRepository
from app.retrospective.infrastructure.persistence.repositories.retro_summary_repo import RetroSummaryRepository
from app.retrospective.infrastructure.persistence.repositories.summary_template_repo import (
    UserSummaryTemplateRepository,
)
from app.shared.infrastructure.config.oauth import GoogleCalendarConfig
from app.shared.infrastructure.config.retrospective import RetrospectiveConfig
from app.shared.infrastructure.config.settings import AppConfig, get_settings
from app.shared.infrastructure.config.topic import TopicConfig
from app.topic.application.services.topic_matcher import TopicMatcher
from app.topic.application.use_cases.create_topic import CreateTopicUseCase
from app.topic.application.use_cases.delete_topic import DeleteTopicUseCase
from app.topic.application.use_cases.generate_digest import GenerateDigestUseCase
from app.topic.application.use_cases.get_digest import GetDigestUseCase
from app.topic.application.use_cases.get_topic_sources import GetTopicSourcesUseCase
from app.topic.application.use_cases.get_topic_stats import GetTopicStatsUseCase
from app.topic.application.use_cases.get_topics import GetTopicsUseCase
from app.topic.application.use_cases.update_topic import UpdateTopicUseCase
from app.topic.domain.repositories.repository import (
    IEmbeddingQueueRepository,
    IEntryChunkRepository,
    ITopicDigestRepository,
    ITopicMatchTransaction,
    ITopicRepository,
    ITodoEmbeddingRepository,
)
from app.topic.infrastructure.ai.embedding_service import EmbeddingService
from app.topic.infrastructure.cache.topic_stats_cache import TopicStatsCache
from app.topic.infrastructure.persistence.repositories.chunk_repo import (
    EmbeddingQueueRepository,
    EntryChunkRepository,
    TodoEmbeddingRepository,
)
from app.topic.infrastructure.persistence.repositories.topic_repo import (
    TopicDigestRepository,
    TopicRepository,
)
from app.topic.infrastructure.persistence.transaction import (
    SqlAlchemyTopicMatchTransaction,
)
from app.todo.application.use_cases.add_calendar_link import AddCalendarLinkUseCase
from app.todo.application.use_cases.create_todo import CreateTodoUseCase
from app.todo.application.use_cases.delete_todo import DeleteTodoUseCase
from app.todo.application.use_cases.get_todo_stats import GetTodoStatsUseCase
from app.todo.application.use_cases.get_todos_by_date import GetTodosByDateUseCase
from app.todo.application.use_cases.get_todos_by_range import GetTodosByRangeUseCase
from app.todo.application.use_cases.remove_calendar_link import RemoveCalendarLinkUseCase
from app.todo.application.use_cases.search_tags import SearchTagsUseCase
from app.todo.application.use_cases.update_todo import UpdateTodoUseCase
from app.todo.domain.repositories.repository import ITodoRepository
from app.todo.infrastructure.persistence.repositories.todo_repo import TodoRepository
from app.user.domain.repositories.country_history_repository import (
    ICountryHistoryRepository,
)
from app.user.domain.repositories.repository import IUserRepository
from app.user.infrastructure.persistence.repositories.country_history_repo import (
    CountryHistoryRepository,
)
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
    def login_attempt_cache(self, config: AppConfig) -> LoginAttemptCache:
        redis = Redis.from_url(config.redis.auth_url, decode_responses=True)
        return LoginAttemptCache(redis, config.auth)

    @provide
    def session_service(
        self, cache: AuthTokenCache, config: AppConfig
    ) -> SessionService:
        return SessionService(cache, config.auth)

    @provide
    def email_verification_cache(self, config: AppConfig) -> EmailVerificationCache:
        redis = Redis.from_url(config.redis.cache_url, decode_responses=True)
        return EmailVerificationCache(redis, config.auth)

    @provide
    def oauth_state_cache(self, config: AppConfig) -> OAuthStateCache:
        redis = Redis.from_url(config.redis.cache_url, decode_responses=True)
        return OAuthStateCache(redis, config.auth)

    @provide
    def onboarding_token_cache(self, config: AppConfig) -> OnboardingTokenCache:
        redis = Redis.from_url(config.redis.cache_url, decode_responses=True)
        return OnboardingTokenCache(redis, config.auth)

    @provide
    def password_reset_cache(self, config: AppConfig) -> PasswordResetCache:
        redis = Redis.from_url(config.redis.cache_url, decode_responses=True)
        return PasswordResetCache(redis, config.auth)

    @provide
    def oauth_client_registry(self, config: AppConfig) -> OAuthClientRegistry:
        return OAuthClientRegistry({
            OAuthProvider.GITHUB: GitHubOAuthClient(config.github_oauth),
            OAuthProvider.GOOGLE: GoogleOAuthClient(config.google_oauth),
        })

    @provide
    def github_api_client(self) -> GitHubApiClient:
        return GitHubApiClient()

    @provide
    def google_calendar_config(self, config: AppConfig) -> GoogleCalendarConfig:
        return config.google_calendar

    @provide
    def google_calendar_api_client(
        self, calendar_config: GoogleCalendarConfig
    ) -> GoogleCalendarApiClient:
        return GoogleCalendarApiClient(calendar_config)

    @provide
    def calendar_oauth_state_cache(self, config: AppConfig) -> CalendarOAuthStateCache:
        redis = Redis.from_url(config.redis.cache_url, decode_responses=True)
        return CalendarOAuthStateCache(
            redis, config.google_calendar.calendar_state_ttl_seconds
        )

    @provide
    def summary_rate_limiter(self, config: AppConfig) -> SummaryRateLimiter:
        redis = Redis.from_url(config.redis.cache_url, decode_responses=True)
        return SummaryRateLimiter(redis)

    @provide
    def retrospective_config(self, config: AppConfig) -> RetrospectiveConfig:
        return config.retrospective

    @provide
    def topic_config(self, config: AppConfig) -> TopicConfig:
        return config.topic

    @provide
    def topic_stats_cache(self, config: AppConfig) -> TopicStatsCache:
        redis = Redis.from_url(config.redis.cache_url, decode_responses=True)
        return TopicStatsCache(redis, config.topic.topic_stats_cache_ttl_seconds)

    @provide
    def embedding_service(self, config: AppConfig) -> EmbeddingService:
        return EmbeddingService(config.ai)


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
    def folder_repo(self, session: AsyncSession) -> IFolderRepository:
        return FolderRepository(session)

    @provide
    def summary_template_repo(
        self, session: AsyncSession
    ) -> IUserSummaryTemplateRepository:
        return UserSummaryTemplateRepository(session)

    @provide
    def retro_template_repo(self, session: AsyncSession) -> IRetroTemplateRepository:
        return RetroTemplateRepository(session)

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

    @provide
    def retrospective_push_repo(
        self, session: AsyncSession
    ) -> IRetrospectivePushRepository:
        return RetrospectivePushRepository(session)

    @provide
    def calendar_connection_repo(
        self, session: AsyncSession
    ) -> IGoogleCalendarConnectionRepository:
        return GoogleCalendarConnectionRepository(session)

    @provide
    def calendar_event_repo(self, session: AsyncSession) -> ICalendarEventRepository:
        return CalendarEventRepository(session)

    @provide
    def country_history_repo(self, session: AsyncSession) -> ICountryHistoryRepository:
        return CountryHistoryRepository(session)

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
    def update_settings_use_case(
        self,
        repo: IUserSettingsRepository,
        github_repo: IGitHubRepositoryRepository,
    ) -> UpdateSettingsUseCase:
        return UpdateSettingsUseCase(repo, github_repo)

    @provide
    def update_country_use_case(
        self,
        user_repo: IUserRepository,
        country_history_repo: ICountryHistoryRepository,
    ) -> UpdateCountryUseCase:
        return UpdateCountryUseCase(user_repo, country_history_repo)

    @provide
    def update_timezone_use_case(self, user_repo: IUserRepository) -> UpdateTimezoneUseCase:
        return UpdateTimezoneUseCase(user_repo)

    @provide
    def list_country_timezones_use_case(self) -> ListCountryTimezonesUseCase:
        return ListCountryTimezonesUseCase()

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
    def seed_retro_templates_use_case(
        self,
        template_repo: IRetroTemplateRepository,
        settings_repo: IUserSettingsRepository,
    ) -> SeedRetroTemplatesUseCase:
        return SeedRetroTemplatesUseCase(template_repo, settings_repo)

    @provide
    def register_use_case(
        self,
        user_repo: IUserRepository,
        verification_cache: EmailVerificationCache,
        session_service: SessionService,
        country_history_repo: ICountryHistoryRepository,
        seed_retro_templates: SeedRetroTemplatesUseCase,
    ) -> RegisterUseCase:
        return RegisterUseCase(
            user_repo, verification_cache, session_service, country_history_repo, seed_retro_templates
        )

    @provide
    def login_use_case(
        self,
        user_repo: IUserRepository,
        session_service: SessionService,
        login_attempts: LoginAttemptCache,
    ) -> LoginUseCase:
        return LoginUseCase(user_repo, session_service, login_attempts)

    @provide
    def refresh_token_use_case(
        self,
        session_service: SessionService,
        user_repo: IUserRepository,
    ) -> RefreshTokenUseCase:
        return RefreshTokenUseCase(session_service, user_repo)

    @provide
    def logout_use_case(self, session_service: SessionService) -> LogoutUseCase:
        return LogoutUseCase(session_service)

    @provide
    def list_sessions_use_case(
        self, session_service: SessionService
    ) -> ListSessionsUseCase:
        return ListSessionsUseCase(session_service)

    @provide
    def revoke_session_use_case(
        self, session_service: SessionService, cache: AuthTokenCache
    ) -> RevokeSessionUseCase:
        return RevokeSessionUseCase(session_service, cache)

    @provide
    def revoke_other_sessions_use_case(
        self, session_service: SessionService
    ) -> RevokeOtherSessionsUseCase:
        return RevokeOtherSessionsUseCase(session_service)

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
    def initiate_oauth_link_use_case(
        self, registry: OAuthClientRegistry, state_cache: OAuthStateCache
    ) -> InitiateOAuthLinkUseCase:
        return InitiateOAuthLinkUseCase(registry, state_cache)

    @provide
    def handle_oauth_callback_use_case(
        self,
        registry: OAuthClientRegistry,
        state_cache: OAuthStateCache,
        oauth_connection_repo: IOAuthConnectionRepository,
        user_repo: IUserRepository,
        session_service: SessionService,
        onboarding_cache: OnboardingTokenCache,
    ) -> HandleOAuthCallbackUseCase:
        return HandleOAuthCallbackUseCase(
            registry,
            state_cache,
            oauth_connection_repo,
            user_repo,
            session_service,
            onboarding_cache,
        )

    @provide
    def request_password_reset_use_case(
        self,
        user_repo: IUserRepository,
        cache: PasswordResetCache,
    ) -> RequestPasswordResetUseCase:
        return RequestPasswordResetUseCase(user_repo, cache)

    @provide
    def reset_password_use_case(
        self,
        user_repo: IUserRepository,
        cache: PasswordResetCache,
        session_service: SessionService,
    ) -> ResetPasswordUseCase:
        return ResetPasswordUseCase(user_repo, cache, session_service)

    @provide
    def complete_onboarding_use_case(
        self,
        onboarding_cache: OnboardingTokenCache,
        user_repo: IUserRepository,
        oauth_connection_repo: IOAuthConnectionRepository,
        session_service: SessionService,
        country_history_repo: ICountryHistoryRepository,
        seed_retro_templates: SeedRetroTemplatesUseCase,
    ) -> CompleteOnboardingUseCase:
        return CompleteOnboardingUseCase(
            onboarding_cache,
            user_repo,
            oauth_connection_repo,
            session_service,
            country_history_repo,
            seed_retro_templates,
        )

    # ── Todo Use Cases ────────────────────────────────────────────────────────

    @provide
    def create_todo_use_case(
        self,
        todo_repo: ITodoRepository,
        settings_repo: IUserSettingsRepository,
    ) -> CreateTodoUseCase:
        return CreateTodoUseCase(todo_repo, settings_repo)

    @provide
    def update_todo_use_case(self, todo_repo: ITodoRepository) -> UpdateTodoUseCase:
        return UpdateTodoUseCase(todo_repo)

    @provide
    def delete_todo_use_case(self, todo_repo: ITodoRepository) -> DeleteTodoUseCase:
        return DeleteTodoUseCase(todo_repo)

    @provide
    def add_calendar_link_use_case(
        self, todo_repo: ITodoRepository
    ) -> AddCalendarLinkUseCase:
        return AddCalendarLinkUseCase(todo_repo)

    @provide
    def remove_calendar_link_use_case(
        self, todo_repo: ITodoRepository
    ) -> RemoveCalendarLinkUseCase:
        return RemoveCalendarLinkUseCase(todo_repo)

    @provide
    def get_todos_by_date_use_case(self, todo_repo: ITodoRepository) -> GetTodosByDateUseCase:
        return GetTodosByDateUseCase(todo_repo)

    @provide
    def get_todos_by_range_use_case(self, todo_repo: ITodoRepository) -> GetTodosByRangeUseCase:
        return GetTodosByRangeUseCase(todo_repo)

    @provide
    def get_todo_stats_use_case(
        self, todo_repo: ITodoRepository, entry_repo: IJournalEntryRepository
    ) -> GetTodoStatsUseCase:
        return GetTodoStatsUseCase(todo_repo, entry_repo)

    @provide
    def search_tags_use_case(self, todo_repo: ITodoRepository) -> SearchTagsUseCase:
        return SearchTagsUseCase(todo_repo)

    # ── Retro Template Use Cases ──────────────────────────────────────────────

    @provide
    def list_retro_templates_use_case(
        self, repo: IRetroTemplateRepository
    ) -> ListRetroTemplatesUseCase:
        return ListRetroTemplatesUseCase(repo)

    @provide
    def create_retro_template_use_case(
        self, repo: IRetroTemplateRepository
    ) -> CreateRetroTemplateUseCase:
        return CreateRetroTemplateUseCase(repo)

    @provide
    def update_retro_template_use_case(
        self, repo: IRetroTemplateRepository
    ) -> UpdateRetroTemplateUseCase:
        return UpdateRetroTemplateUseCase(repo)

    @provide
    def delete_retro_template_use_case(
        self,
        template_repo: IRetroTemplateRepository,
        settings_repo: IUserSettingsRepository,
    ) -> DeleteRetroTemplateUseCase:
        return DeleteRetroTemplateUseCase(template_repo, settings_repo)

    @provide
    def reset_retro_template_use_case(
        self, repo: IRetroTemplateRepository
    ) -> ResetRetroTemplateUseCase:
        return ResetRetroTemplateUseCase(repo)

    @provide
    def set_active_retro_template_use_case(
        self,
        template_repo: IRetroTemplateRepository,
        settings_repo: IUserSettingsRepository,
    ) -> SetActiveRetroTemplateUseCase:
        return SetActiveRetroTemplateUseCase(template_repo, settings_repo)

    # ── Journal Entry Use Cases ───────────────────────────────────────────────

    @provide
    def create_entry_use_case(
        self,
        entry_repo: IJournalEntryRepository,
        settings_repo: IUserSettingsRepository,
    ) -> CreateEntryUseCase:
        return CreateEntryUseCase(entry_repo, settings_repo)

    @provide
    def upsert_entry_use_case(
        self,
        entry_repo: IJournalEntryRepository,
        settings_repo: IUserSettingsRepository,
    ) -> UpsertEntryUseCase:
        return UpsertEntryUseCase(entry_repo, settings_repo)

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
    def get_entries_page_use_case(
        self, entry_repo: IJournalEntryRepository, summary_repo: IRetroSummaryRepository
    ) -> GetEntriesPageUseCase:
        return GetEntriesPageUseCase(entry_repo, summary_repo)

    @provide
    def global_search_use_case(
        self, todo_repo: ITodoRepository, entry_repo: IJournalEntryRepository
    ) -> GlobalSearchUseCase:
        return GlobalSearchUseCase(todo_repo, entry_repo)

    @provide
    def delete_entry_use_case(
        self, entry_repo: IJournalEntryRepository
    ) -> DeleteEntryUseCase:
        return DeleteEntryUseCase(entry_repo)

    # ── Folder Use Cases ──────────────────────────────────────────────────────

    @provide
    def create_folder_use_case(self, folder_repo: IFolderRepository) -> CreateFolderUseCase:
        return CreateFolderUseCase(folder_repo)

    @provide
    def list_folders_use_case(self, folder_repo: IFolderRepository) -> ListFoldersUseCase:
        return ListFoldersUseCase(folder_repo)

    @provide
    def update_folder_use_case(self, folder_repo: IFolderRepository) -> UpdateFolderUseCase:
        return UpdateFolderUseCase(folder_repo)

    @provide
    def delete_folder_use_case(self, folder_repo: IFolderRepository) -> DeleteFolderUseCase:
        return DeleteFolderUseCase(folder_repo)

    @provide
    def get_folder_contents_use_case(
        self,
        folder_repo: IFolderRepository,
        entry_repo: IJournalEntryRepository,
        summary_repo: IRetroSummaryRepository,
    ) -> GetFolderContentsUseCase:
        return GetFolderContentsUseCase(folder_repo, entry_repo, summary_repo)

    @provide
    def move_entry_to_folder_use_case(
        self,
        entry_repo: IJournalEntryRepository,
        summary_repo: IRetroSummaryRepository,
        folder_repo: IFolderRepository,
    ) -> MoveEntryToFolderUseCase:
        return MoveEntryToFolderUseCase(entry_repo, summary_repo, folder_repo)

    # ── Summary Use Cases ─────────────────────────────────────────────────────

    @provide
    def request_summary_use_case(
        self,
        summary_repo: IRetroSummaryRepository,
        rate_limiter: SummaryRateLimiter,
    ) -> RequestSummaryUseCase:
        return RequestSummaryUseCase(summary_repo, rate_limiter)

    @provide
    def get_summary_usage_use_case(
        self, rate_limiter: SummaryRateLimiter
    ) -> GetSummaryUsageUseCase:
        return GetSummaryUsageUseCase(rate_limiter)

    @provide
    def create_summary_template_use_case(
        self,
        repo: IUserSummaryTemplateRepository,
        config: RetrospectiveConfig,
    ) -> CreateSummaryTemplateUseCase:
        return CreateSummaryTemplateUseCase(repo, config)

    @provide
    def update_summary_template_use_case(
        self, repo: IUserSummaryTemplateRepository
    ) -> UpdateSummaryTemplateUseCase:
        return UpdateSummaryTemplateUseCase(repo)

    @provide
    def delete_summary_template_use_case(
        self,
        template_repo: IUserSummaryTemplateRepository,
        settings_repo: IUserSettingsRepository,
    ) -> DeleteSummaryTemplateUseCase:
        return DeleteSummaryTemplateUseCase(template_repo, settings_repo)

    @provide
    def list_summary_templates_use_case(
        self, repo: IUserSummaryTemplateRepository
    ) -> ListSummaryTemplatesUseCase:
        return ListSummaryTemplatesUseCase(repo)

    @provide
    def get_summary_template_use_case(
        self, repo: IUserSummaryTemplateRepository
    ) -> GetSummaryTemplateUseCase:
        return GetSummaryTemplateUseCase(repo)

    @provide
    def set_active_summary_template_use_case(
        self,
        template_repo: IUserSummaryTemplateRepository,
        settings_repo: IUserSettingsRepository,
    ) -> SetActiveSummaryTemplateUseCase:
        return SetActiveSummaryTemplateUseCase(template_repo, settings_repo)

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

    @provide
    def edit_summary_use_case(
        self, summary_repo: IRetroSummaryRepository
    ) -> EditSummaryUseCase:
        return EditSummaryUseCase(summary_repo)

    @provide
    def get_summary_readiness_use_case(
        self, entry_repo: IJournalEntryRepository
    ) -> GetSummaryReadinessUseCase:
        return GetSummaryReadinessUseCase(entry_repo)

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

    @provide
    def get_connection_status_use_case(
        self,
        oauth_repo: IOAuthConnectionRepository,
        settings_repo: IUserSettingsRepository,
        api_client: GitHubApiClient,
    ) -> GetConnectionStatusUseCase:
        return GetConnectionStatusUseCase(oauth_repo, settings_repo, api_client)

    @provide
    def update_repository_use_case(
        self, repo: IGitHubRepositoryRepository
    ) -> UpdateRepositoryUseCase:
        return UpdateRepositoryUseCase(repo)

    @provide
    def get_commits_by_date_use_case(
        self,
        user_repo: IUserRepository,
        oauth_repo: IOAuthConnectionRepository,
        repo: IGitHubRepositoryRepository,
        api_client: GitHubApiClient,
    ) -> GetCommitsByDateUseCase:
        return GetCommitsByDateUseCase(user_repo, oauth_repo, repo, api_client)

    @provide
    def push_retrospective_use_case(
        self,
        settings_repo: IUserSettingsRepository,
        oauth_repo: IOAuthConnectionRepository,
        repo: IGitHubRepositoryRepository,
        api_client: GitHubApiClient,
        push_repo: IRetrospectivePushRepository,
    ) -> PushRetrospectiveUseCase:
        return PushRetrospectiveUseCase(
            settings_repo, oauth_repo, repo, api_client, push_repo
        )

    # ── Google Calendar Use Cases ─────────────────────────────────────────────

    @provide
    def initiate_calendar_connect_use_case(
        self,
        api_client: GoogleCalendarApiClient,
        state_cache: CalendarOAuthStateCache,
    ) -> InitiateCalendarConnectUseCase:
        return InitiateCalendarConnectUseCase(api_client, state_cache)

    @provide
    def handle_calendar_callback_use_case(
        self,
        api_client: GoogleCalendarApiClient,
        state_cache: CalendarOAuthStateCache,
        connection_repo: IGoogleCalendarConnectionRepository,
        todo_repo: ITodoRepository,
    ) -> HandleCalendarCallbackUseCase:
        return HandleCalendarCallbackUseCase(
            api_client, state_cache, connection_repo, todo_repo
        )

    @provide
    def get_calendar_connection_status_use_case(
        self, connection_repo: IGoogleCalendarConnectionRepository
    ) -> GetCalendarConnectionStatusUseCase:
        return GetCalendarConnectionStatusUseCase(connection_repo)

    @provide
    def sync_calendar_events_use_case(
        self,
        connection_repo: IGoogleCalendarConnectionRepository,
        event_repo: ICalendarEventRepository,
        api_client: GoogleCalendarApiClient,
        calendar_config: GoogleCalendarConfig,
        todo_repo: ITodoRepository,
        settings_repo: IUserSettingsRepository,
    ) -> SyncCalendarEventsUseCase:
        return SyncCalendarEventsUseCase(
            connection_repo, event_repo, api_client, calendar_config, todo_repo, settings_repo
        )

    @provide
    def get_calendar_events_use_case(
        self,
        sync_use_case: SyncCalendarEventsUseCase,
        event_repo: ICalendarEventRepository,
        connection_repo: IGoogleCalendarConnectionRepository,
    ) -> GetCalendarEventsUseCase:
        return GetCalendarEventsUseCase(sync_use_case, event_repo, connection_repo)

    @provide
    def disconnect_calendar_use_case(
        self,
        connection_repo: IGoogleCalendarConnectionRepository,
        event_repo: ICalendarEventRepository,
        todo_repo: ITodoRepository,
    ) -> DisconnectCalendarUseCase:
        return DisconnectCalendarUseCase(connection_repo, event_repo, todo_repo)

    # ── Topic Repositories ────────────────────────────────────────────────────

    @provide
    def topic_repo(self, session: AsyncSession) -> ITopicRepository:
        return TopicRepository(session)

    @provide
    def topic_digest_repo(self, session: AsyncSession) -> ITopicDigestRepository:
        return TopicDigestRepository(session)

    @provide
    def entry_chunk_repo(self, session: AsyncSession) -> IEntryChunkRepository:
        return EntryChunkRepository(session)

    @provide
    def todo_embedding_repo(self, session: AsyncSession) -> ITodoEmbeddingRepository:
        return TodoEmbeddingRepository(session)

    @provide
    def embedding_queue_repo(self, session: AsyncSession) -> IEmbeddingQueueRepository:
        return EmbeddingQueueRepository(session)

    # ── Topic Use Cases ───────────────────────────────────────────────────────

    @provide
    def create_topic_use_case(
        self,
        repo: ITopicRepository,
        config: TopicConfig,
    ) -> CreateTopicUseCase:
        return CreateTopicUseCase(repo, config)

    @provide
    def delete_topic_use_case(self, repo: ITopicRepository) -> DeleteTopicUseCase:
        return DeleteTopicUseCase(repo)

    @provide
    def update_topic_use_case(self, repo: ITopicRepository) -> UpdateTopicUseCase:
        return UpdateTopicUseCase(repo)

    @provide
    def topic_match_transaction(self, session: AsyncSession) -> ITopicMatchTransaction:
        # entry_repo/todo_repo/chunk_repo 와 같은 요청 스코프 세션이어야 SAVEPOINT 가
        # 그 리포지터리들이 실제로 쓰는 트랜잭션 위에서 열린다.
        return SqlAlchemyTopicMatchTransaction(session)

    @provide
    def topic_matcher(
        self,
        embedding_service: EmbeddingService,
        chunk_repo: IEntryChunkRepository,
        todo_emb_repo: ITodoEmbeddingRepository,
        entry_repo: IJournalEntryRepository,
        todo_repo: ITodoRepository,
        cache: TopicStatsCache,
        config: TopicConfig,
        transaction: ITopicMatchTransaction,
    ) -> TopicMatcher:
        return TopicMatcher(
            embedding_service,
            chunk_repo,
            todo_emb_repo,
            entry_repo,
            todo_repo,
            cache,
            config,
            transaction,
        )

    @provide
    def get_topics_use_case(
        self,
        repo: ITopicRepository,
        digest_repo: ITopicDigestRepository,
        matcher: TopicMatcher,
    ) -> GetTopicsUseCase:
        return GetTopicsUseCase(repo, digest_repo, matcher)

    @provide
    def get_topic_stats_use_case(
        self,
        topic_repo: ITopicRepository,
        digest_repo: ITopicDigestRepository,
        matcher: TopicMatcher,
    ) -> GetTopicStatsUseCase:
        return GetTopicStatsUseCase(topic_repo, digest_repo, matcher)

    @provide
    def get_topic_sources_use_case(
        self,
        topic_repo: ITopicRepository,
        digest_repo: ITopicDigestRepository,
        matcher: TopicMatcher,
    ) -> GetTopicSourcesUseCase:
        return GetTopicSourcesUseCase(topic_repo, digest_repo, matcher)

    @provide
    def generate_digest_use_case(
        self,
        topic_repo: ITopicRepository,
        digest_repo: ITopicDigestRepository,
    ) -> GenerateDigestUseCase:
        return GenerateDigestUseCase(topic_repo, digest_repo)

    @provide
    def get_digest_use_case(
        self,
        topic_repo: ITopicRepository,
        digest_repo: ITopicDigestRepository,
    ) -> GetDigestUseCase:
        return GetDigestUseCase(topic_repo, digest_repo)
