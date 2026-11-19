from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.ai.domain.models.ai_settings import AiMemory, AiSchedule, AiSettings
from app.ai.domain.models.conversation import ChatMessage, Conversation, Proposal
from app.ai.domain.models.suggestion import AiUsageReport, Suggestion


class SuggestionActionResponse(BaseModel):
    label: str
    patch: dict[str, Any]  # PATCH /todos/{id} 본문 모양 — FE 는 보여 주기만 하고 적용은 서버가 한다


class SuggestionResponse(BaseModel):
    id: str
    kind: str
    todo_id: str = Field(serialization_alias="todoId")
    title: str
    reason: str
    slot: dict[str, str] | None = None  # {start, end} ISO — 캘린더 흐린 칸
    actions: list[SuggestionActionResponse]
    status: str

    model_config = {"populate_by_name": True}

    @classmethod
    def from_entity(cls, s: Suggestion) -> "SuggestionResponse":
        return cls(
            id=s.id,
            kind=s.kind,
            todo_id=s.todo_id,
            title=s.payload.get("title", ""),
            reason=s.payload.get("reason", ""),
            slot=s.payload.get("slot"),
            actions=[SuggestionActionResponse(label=a.label, patch=a.patch) for a in s.actions],
            status=s.status,
        )


class ApplySuggestionResponse(BaseModel):
    suggestion: SuggestionResponse
    todo_id: str = Field(serialization_alias="todoId")  # 바뀐 할 일(가상 회차였으면 새 id)
    undo_token: str = Field(serialization_alias="undoToken")  # POST /ai/suggestions/{id}/undo 의 id

    model_config = {"populate_by_name": True}


class UsageWindowResponse(BaseModel):
    used: int
    limit: int


class AiUsageResponse(BaseModel):
    day: UsageWindowResponse
    month: UsageWindowResponse

    @classmethod
    def from_report(cls, r: AiUsageReport) -> "AiUsageResponse":
        return cls(
            day=UsageWindowResponse(used=r.day_used, limit=r.day_limit),
            month=UsageWindowResponse(used=r.month_used, limit=r.month_limit),
        )


class ConversationResponse(BaseModel):
    id: str
    title: str
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime | None = Field(serialization_alias="updatedAt")

    model_config = {"populate_by_name": True}

    @classmethod
    def from_entity(cls, c: Conversation) -> "ConversationResponse":
        return cls(id=c.id, title=c.title, created_at=c.created_at, updated_at=c.updated_at)


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    tool_calls: list[dict[str, Any]] = Field(serialization_alias="toolCalls")
    created_at: datetime = Field(serialization_alias="createdAt")

    model_config = {"populate_by_name": True}

    @classmethod
    def from_entity(cls, m: ChatMessage) -> "MessageResponse":
        return cls(
            id=m.id,
            role=m.role,
            content=m.content,
            tool_calls=m.tool_calls,
            created_at=m.created_at,
        )


class ProposalResponse(BaseModel):
    id: str
    kind: str
    summary: str
    # [{key, todoId, title, before, after, clash}]
    # after 의 시각은 UTC ISO, clash 는 같은 시간에 이미 있는 할 일 id
    items: list[dict[str, Any]]
    status: str
    applied: dict[str, Any] | None = None
    conversation_id: str | None = Field(default=None, serialization_alias="conversationId")

    model_config = {"populate_by_name": True}

    @classmethod
    def from_entity(cls, p: Proposal) -> "ProposalResponse":
        return cls(
            id=p.id,
            kind=p.kind,
            summary=p.payload.get("summary", ""),
            items=p.items,
            status=p.status,
            applied=p.applied,
            conversation_id=p.conversation_id,
        )


class UndoProposalResponse(BaseModel):
    proposal: ProposalResponse
    skipped: list[str]  # 적용 뒤 사용자가 고쳐서 되돌리지 않은 항목 key


class AiSettingsResponse(BaseModel):
    pet_enabled: bool = Field(serialization_alias="petEnabled")
    tools: dict[str, bool]
    confirm_mode: str = Field(serialization_alias="confirmMode")
    answer_length: str = Field(serialization_alias="answerLength")
    deep_search: bool = Field(serialization_alias="deepSearch")
    memory_enabled: bool = Field(serialization_alias="memoryEnabled")
    retention_days: int = Field(serialization_alias="retentionDays")

    model_config = {"populate_by_name": True}

    @classmethod
    def from_entity(cls, s: AiSettings) -> "AiSettingsResponse":
        return cls(
            pet_enabled=s.pet_enabled,
            tools=s.tools,
            confirm_mode=s.confirm_mode,
            answer_length=s.answer_length,
            deep_search=s.deep_search,
            memory_enabled=s.memory_enabled,
            retention_days=s.retention_days,
        )


class MemoryResponse(BaseModel):
    id: str
    text: str
    created_at: datetime = Field(serialization_alias="createdAt")

    model_config = {"populate_by_name": True}

    @classmethod
    def from_entity(cls, m: AiMemory) -> "MemoryResponse":
        return cls(id=m.id, text=m.text, created_at=m.created_at)


class ScheduleResponse(BaseModel):
    id: str
    prompt: str
    repeat: dict[str, Any]
    enabled: bool
    last_run_date: str | None = Field(serialization_alias="lastRunDate")
    created_at: datetime = Field(serialization_alias="createdAt")

    model_config = {"populate_by_name": True}

    @classmethod
    def from_entity(cls, s: AiSchedule) -> "ScheduleResponse":
        return cls(
            id=s.id,
            prompt=s.prompt,
            repeat=s.repeat,
            enabled=s.enabled,
            last_run_date=s.last_run_date.isoformat() if s.last_run_date else None,
            created_at=s.created_at,
        )
