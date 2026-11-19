from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.application.ports import ChatModelPort, CommitPort, RetroPort, TodoPort
from app.ai.application.use_cases.ai_settings import AiSettingsUseCase
from app.ai.application.use_cases.conversations import (
    ConversationsUseCase,
    PostMessageUseCase,
    RunAiTurnUseCase,
)
from app.ai.application.use_cases.proposals import ProposalsUseCase
from app.ai.application.use_cases.suggestions import (
    ApplySuggestionUseCase,
    DismissSuggestionUseCase,
    GetSuggestionsUseCase,
    SuggestionService,
    UndoSuggestionUseCase,
)
from app.ai.application.use_cases.usage import AiUsageService, GetAiUsageUseCase
from app.ai.domain.repositories.repository import (
    IAiRetentionRepository,
    IAiSettingsRepository,
    IAiUsageRepository,
    IConversationRepository,
    IProposalRepository,
    ISuggestionRepository,
)
from app.ai.infrastructure.adapters.commit_adapter import CommitAdapter
from app.ai.infrastructure.adapters.retro_adapter import RetroAdapter
from app.ai.infrastructure.adapters.todo_adapter import TodoAdapter
from app.ai.infrastructure.llm.gemini_chat import GeminiChatModel
from app.ai.infrastructure.persistence.repositories.ai_settings_repo import (
    AiRetentionRepository,
    AiSettingsRepository,
)
from app.ai.infrastructure.persistence.repositories.conversation_repo import (
    ConversationRepository,
    ProposalRepository,
)
from app.ai.infrastructure.persistence.repositories.suggestion_repo import (
    AiUsageRepository,
    SuggestionRepository,
)
from app.shared.infrastructure.config.settings import AppConfig
from app.user.domain.repositories.repository import IUserRepository


class AiProvider(Provider):
    """AI 모듈 — 추천·사용량. 다른 모듈 기능은 어댑터(포트 구현)로만 쓴다."""

    scope = Scope.REQUEST

    @provide
    def suggestion_repo(self, session: AsyncSession) -> ISuggestionRepository:
        return SuggestionRepository(session)

    @provide
    def usage_repo(self, session: AsyncSession) -> IAiUsageRepository:
        return AiUsageRepository(session)

    @provide
    def conversation_repo(self, session: AsyncSession) -> IConversationRepository:
        return ConversationRepository(session)

    @provide
    def proposal_repo(self, session: AsyncSession) -> IProposalRepository:
        return ProposalRepository(session)

    @provide
    def ai_settings_repo(self, session: AsyncSession) -> IAiSettingsRepository:
        return AiSettingsRepository(session)

    ai_settings = provide(AiSettingsUseCase)

    @provide
    def ai_retention_repo(self, session: AsyncSession) -> IAiRetentionRepository:
        return AiRetentionRepository(session)

    todo_port = provide(TodoAdapter, provides=TodoPort)
    commit_port = provide(CommitAdapter, provides=CommitPort)
    retro_port = provide(RetroAdapter, provides=RetroPort)

    @provide(scope=Scope.APP)
    def chat_model(self, config: AppConfig) -> ChatModelPort:
        return GeminiChatModel(config.ai)

    conversations = provide(ConversationsUseCase)
    post_message = provide(PostMessageUseCase)
    run_turn = provide(RunAiTurnUseCase)
    proposals = provide(ProposalsUseCase)

    suggestion_service = provide(SuggestionService)
    get_suggestions = provide(GetSuggestionsUseCase)
    apply_suggestion = provide(ApplySuggestionUseCase)
    undo_suggestion = provide(UndoSuggestionUseCase)
    dismiss_suggestion = provide(DismissSuggestionUseCase)

    @provide
    def usage_service(
        self, repo: IAiUsageRepository, user_repo: IUserRepository, config: AppConfig
    ) -> AiUsageService:
        return AiUsageService(
            repo, user_repo, config.ai.ai_daily_request_limit, config.ai.ai_monthly_request_limit
        )

    get_usage = provide(GetAiUsageUseCase)
