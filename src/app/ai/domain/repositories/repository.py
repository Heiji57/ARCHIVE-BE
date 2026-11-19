from abc import ABC, abstractmethod
from datetime import date, datetime

from app.ai.domain.models.ai_settings import AiMemory, AiSchedule, AiSettings
from app.ai.domain.models.conversation import ChatMessage, Conversation, Proposal
from app.ai.domain.models.suggestion import Suggestion


class ISuggestionRepository(ABC):
    @abstractmethod
    async def list_for_date(self, user_id: str, date_key: str) -> list[Suggestion]: ...

    @abstractmethod
    async def find_by_id(
        self, suggestion_id: str, user_id: str, for_update: bool = False
    ) -> Suggestion | None:
        """for_update 면 행을 잠근다 — 적용·되돌리기를 두 번 눌러도 한 번만 처리되게."""
        ...

    @abstractmethod
    async def insert_if_absent(self, suggestion: Suggestion) -> Suggestion:
        """같은 (날짜, 종류, 할 일) 행이 없으면 넣고, 있으면 그 행을 돌려준다.

        동시 요청이 먼저 넣었어도 유니크 위반 없이 한 행이 된다.
        """
        ...

    @abstractmethod
    async def save(self, suggestion: Suggestion) -> Suggestion: ...


class IAiUsageRepository(ABC):
    @abstractmethod
    async def requests_on(self, user_id: str, date_key: str) -> int: ...

    @abstractmethod
    async def requests_in_month(self, user_id: str, month_prefix: str) -> int:
        """month_prefix = "YYYY-MM"."""
        ...

    @abstractmethod
    async def add(
        self, user_id: str, date_key: str, requests: int, input_tokens: int, output_tokens: int
    ) -> None:
        """그날 사용량에 더한다(행이 없으면 만든다)."""
        ...


class IConversationRepository(ABC):
    @abstractmethod
    async def save(self, conversation: Conversation) -> Conversation: ...

    @abstractmethod
    async def find_by_id(self, conversation_id: str, user_id: str) -> Conversation | None: ...

    @abstractmethod
    async def list_by_user(self, user_id: str, limit: int = 50) -> list[Conversation]:
        """최근 대화순(updated_at, created_at 내림차순)."""
        ...

    @abstractmethod
    async def delete(self, conversation_id: str, user_id: str) -> None: ...

    @abstractmethod
    async def add_message(self, message: ChatMessage) -> ChatMessage: ...

    @abstractmethod
    async def list_messages(
        self, conversation_id: str, limit: int | None = None
    ) -> list[ChatMessage]:
        """오래된 순. limit 이 있으면 최근 limit 개."""
        ...


class IProposalRepository(ABC):
    @abstractmethod
    async def save(self, proposal: Proposal) -> Proposal: ...

    @abstractmethod
    async def find_by_id(
        self, proposal_id: str, user_id: str, for_update: bool = False
    ) -> Proposal | None:
        """for_update 면 행을 잠근다 — 적용·되돌리기를 두 번 눌러도 한 번만."""
        ...

    @abstractmethod
    async def list_by_conversation(self, conversation_id: str) -> list[Proposal]: ...


class IAiSettingsRepository(ABC):
    @abstractmethod
    async def find(self, user_id: str) -> AiSettings | None: ...

    @abstractmethod
    async def save(self, settings: AiSettings) -> AiSettings: ...

    @abstractmethod
    async def list_memories(self, user_id: str) -> list[AiMemory]: ...

    @abstractmethod
    async def add_memory(self, memory: AiMemory) -> AiMemory: ...

    @abstractmethod
    async def delete_memory(self, memory_id: str, user_id: str) -> bool:
        """지웠으면 True."""
        ...

    @abstractmethod
    async def list_schedules(self, user_id: str) -> list[AiSchedule]: ...

    @abstractmethod
    async def find_schedule(self, schedule_id: str, user_id: str) -> AiSchedule | None: ...

    @abstractmethod
    async def save_schedule(self, schedule: AiSchedule) -> AiSchedule: ...

    @abstractmethod
    async def delete_schedule(self, schedule_id: str, user_id: str) -> bool: ...

    @abstractmethod
    async def claim_run(self, schedule_id: str, run_date: date) -> bool:
        """오늘 실행 차례를 가져간다 — 아직 오늘 안 돌렸을 때만 True.

        원자적이고, 다른 필드(프롬프트·켜짐)는 건드리지 않는다.
        """
        ...

    @abstractmethod
    async def list_enabled_schedules(self) -> list[AiSchedule]:
        """모든 사용자의 켜진 예약 — 예약 dispatcher 용."""
        ...


class IAiRetentionRepository(ABC):
    @abstractmethod
    async def purge_older_than(self, user_id: str, before: datetime) -> int:
        """updated_at(없으면 created_at)이 before 이전인 대화를 지운다(메시지 함께). 적용 안 한
        제안(pending/dismissed)도 지운다 — 적용한 제안은 되돌리기 기록이라 남긴다. 지운 대화 수."""
        ...
