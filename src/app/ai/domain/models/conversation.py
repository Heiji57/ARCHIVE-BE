from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from app.shared.domain.models.base import BaseEntity

ProposalKind = Literal["add", "move", "retro_draft"]
ProposalStatus = Literal["pending", "applied", "dismissed", "undone"]


@dataclass(kw_only=True)
class Conversation(BaseEntity):
    user_id: str
    title: str = ""


@dataclass(kw_only=True)
class ChatMessage(BaseEntity):
    conversation_id: str
    role: Literal["user", "assistant"]
    content: str
    # assistant 차례에서 부른 도구 기록(이름·인자·결과 요약) — 대화 기록 화면과 디버깅용
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    context: dict[str, Any] | None = None  # 사용자 메시지에 FE 가 붙인 화면 맥락(선택한 날짜 등)


@dataclass(kw_only=True)
class Proposal(BaseEntity):
    """AI 가 만든 변경 제안. 사용자가 적용하기 전에는 아무것도 바뀌지 않는다.

    payload = {summary, items: [{key, todoId, title, before, after, clash}]}
    applied = {item_key: {todo_id|entry_id, created: bool, previous: {...}, after: {...}}}
    """

    user_id: str
    conversation_id: str | None
    kind: ProposalKind
    payload: dict[str, Any] = field(default_factory=dict)
    status: ProposalStatus = "pending"
    applied: dict[str, Any] | None = None
    applied_at: datetime | None = None

    @property
    def items(self) -> list[dict[str, Any]]:
        return list(self.payload.get("items", []))
