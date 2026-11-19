"""AI 대화(5b) — 대화·메시지 관리와 한 차례 실행.

`POST /ai/conversations/{id}/messages` 는 사용량을 확인하고 사용자 메시지만 저장한 뒤(202)
워커(`worker.run_ai_turn`)가 `RunAiTurnUseCase` 로 차례를 돌린다. 진행은 SSE 로 흐른다.
"""

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.ai.application.ports import ChatModelPort, CommitPort, EventSink, RetroPort, TodoPort
from app.ai.application.services.agent import AgentContext, AgentOutcome, run_turn
from app.ai.application.use_cases.usage import AiUsageService
from app.ai.domain.exceptions.exceptions import AiConversationNotFoundException
from app.ai.domain.models.conversation import ChatMessage, Conversation
from app.ai.domain.repositories.repository import IConversationRepository, IProposalRepository
from app.settings.domain.models.user_settings import UserSettings
from app.settings.domain.repositories.repository import IUserSettingsRepository
from app.shared.domain.utils.id import generate_id
from app.user.domain.repositories.repository import IUserRepository

_TITLE_LEN = 60


class MessageNotYetVisibleError(Exception):
    """워커가 요청 트랜잭션 커밋보다 먼저 돌아 사용자 메시지가 아직 안 보임 — 잠시 뒤 다시."""


async def _owned(repo: IConversationRepository, user_id: str, conversation_id: str) -> Conversation:
    conversation = await repo.find_by_id(conversation_id, user_id)
    if conversation is None:
        raise AiConversationNotFoundException()
    return conversation


class ConversationsUseCase:
    """대화 목록·생성·삭제·메시지 조회 — 얇은 CRUD 를 한 클래스로."""

    def __init__(self, repo: IConversationRepository) -> None:
        self._repo = repo

    async def create(self, user_id: str, title: str = "") -> Conversation:
        now = datetime.now(UTC)
        return await self._repo.save(
            Conversation(
                id=generate_id("conv"),
                user_id=user_id,
                title=title.strip()[:_TITLE_LEN],
                created_at=now,
                updated_at=now,
            )
        )

    async def list_all(self, user_id: str) -> list[Conversation]:
        return await self._repo.list_by_user(user_id)

    async def delete(self, user_id: str, conversation_id: str) -> None:
        await _owned(self._repo, user_id, conversation_id)
        await self._repo.delete(conversation_id, user_id)

    async def messages(self, user_id: str, conversation_id: str) -> list[ChatMessage]:
        await _owned(self._repo, user_id, conversation_id)
        return await self._repo.list_messages(conversation_id)

    async def record_failure(self, user_id: str, conversation_id: str, code: str) -> None:
        """실패한 차례를 기록한다 — 늦게 구독한 SSE 가 시간 초과 대신 실제 오류를 받게."""
        await _owned(self._repo, user_id, conversation_id)
        await self._repo.add_message(
            ChatMessage(
                id=generate_id("msg"),
                conversation_id=conversation_id,
                role="assistant",
                content="",
                context={"error": code},
                created_at=datetime.now(UTC),
            )
        )


class PostMessageUseCase:
    def __init__(self, repo: IConversationRepository, usage: AiUsageService) -> None:
        self._repo = repo
        self._usage = usage

    async def execute(
        self, user_id: str, conversation_id: str, text: str, context: dict[str, Any] | None
    ) -> ChatMessage:
        """사용량을 먼저 확인(넘으면 429)하고 사용자 메시지를 저장한다. 첫 메시지가 제목이 된다."""
        conversation = await _owned(self._repo, user_id, conversation_id)
        await self._usage.check(user_id)
        now = datetime.now(UTC)
        message = await self._repo.add_message(
            ChatMessage(
                id=generate_id("msg"),
                conversation_id=conversation_id,
                role="user",
                content=text,
                context=context,
                created_at=now,
            )
        )
        await self._repo.save(
            replace(
                conversation,
                title=conversation.title or text.strip()[:_TITLE_LEN],
                updated_at=now,
            )
        )
        return message


class RunAiTurnUseCase:
    """워커에서 한 차례 — 기록을 읽어 모델과 도구를 돌리고, 답을 저장하고, 사용량을 쌓는다."""

    def __init__(
        self,
        repo: IConversationRepository,
        proposals: IProposalRepository,
        todos: TodoPort,
        commits: CommitPort,
        retros: RetroPort,
        chat: ChatModelPort,
        usage: AiUsageService,
        settings_repo: IUserSettingsRepository,
        user_repo: IUserRepository,
    ) -> None:
        self._repo = repo
        self._proposals = proposals
        self._todos = todos
        self._commits = commits
        self._retros = retros
        self._chat = chat
        self._usage = usage
        self._settings_repo = settings_repo
        self._user_repo = user_repo

    async def execute(
        self,
        user_id: str,
        conversation_id: str,
        sink: EventSink,
        expect_message_id: str | None = None,
        enabled_sources: frozenset[str] | None = None,
        memories: list[str] | None = None,
        answer_length: str = "normal",
    ) -> tuple[AgentOutcome, str]:
        """(결과, 저장한 답 메시지 id). `done` 이벤트는 호출자가 **커밋 뒤** 보낸다 — 그래야 FE 가
        done 을 받고 메시지를 다시 읽을 때 답이 보인다."""
        conversation = await _owned(self._repo, user_id, conversation_id)
        settings = await self._settings_repo.find_by_user_id(user_id) or UserSettings.default(
            user_id
        )
        user = await self._user_repo.find_by_id(user_id)
        ctx = AgentContext(
            user_id=user_id,
            conversation_id=conversation.id,
            settings=settings,
            tz=ZoneInfo(user.timezone if user else "UTC"),
            now=datetime.now(UTC),
            todos=self._todos,
            commits=self._commits,
            retros=self._retros,
            proposals=self._proposals,
            sink=sink,
            memories=memories or [],
            answer_length=answer_length,
        )
        if enabled_sources is not None:
            ctx.enabled_sources = enabled_sources
        history = await self._repo.list_messages(conversation.id, limit=40)
        if expect_message_id and all(m.id != expect_message_id for m in history):
            raise MessageNotYetVisibleError(expect_message_id)
        outcome = await run_turn(ctx, history, self._chat)
        message = await self._repo.add_message(
            ChatMessage(
                id=generate_id("msg"),
                conversation_id=conversation.id,
                role="assistant",
                content=outcome.text,
                tool_calls=outcome.tool_log,
                created_at=datetime.now(UTC),
            )
        )
        await self._repo.save(replace(conversation, updated_at=message.created_at))
        await self._usage.record(user_id, outcome.input_tokens, outcome.output_tokens)
        return outcome, message.id
