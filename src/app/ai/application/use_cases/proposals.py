"""AI 제안(5b) — 적용(고른 항목만), 되돌리기, 넘기기.

적용은 요청 트랜잭션 하나에서 한다 — 한 항목이라도 실패하면 전부 롤백된다.
- add: 새 할 일(POST /todos 규칙) · move: 날짜·시간 바꾸기(PATCH 규칙) · retro_draft: 일간 회고
- 적용 전, 제안이 본 값(before)과 지금 값이 다르면 409 AI_PROPOSAL_STALE(그사이 사용자가 고침).
되돌리기는 적용한 것만 — 만든 할 일은 지우고, 바꾼 할 일은 이전 값으로. 적용 뒤 사용자가
그 할 일을 또 고쳤으면 그 항목은 건드리지 않고 `skipped` 로 알려 준다.
"""

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from app.ai.application.ports import RetroPort, TodoPort
from app.ai.domain.exceptions.exceptions import (
    AiProposalAlreadyAppliedException,
    AiProposalItemsInvalidException,
    AiProposalNotFoundException,
    AiProposalStaleException,
    AiProposalStateInvalidException,
)
from app.ai.domain.models.conversation import Proposal
from app.ai.domain.models.snapshots import TodoSnapshot
from app.ai.domain.repositories.repository import IProposalRepository


def _same_instant(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is b
    return datetime.fromisoformat(str(a)) == datetime.fromisoformat(str(b))


def _matches(todo: TodoSnapshot, values: dict[str, Any]) -> bool:
    """values 의 date_key/start_time/end_time 이 지금 할 일과 같은지."""
    times: dict[str, datetime | None] = {"start_time": todo.start_time, "end_time": todo.end_time}
    for key, expected in values.items():
        if key == "date_key" and todo.date_key != expected:
            return False
        if key in times:
            value = times[key]
            if not _same_instant(value.isoformat() if value else None, expected):
                return False
    return True


@dataclass(frozen=True)
class UndoResult:
    proposal: Proposal
    skipped: list[str]


class ProposalsUseCase:
    def __init__(self, repo: IProposalRepository, todos: TodoPort, retros: RetroPort) -> None:
        self._repo = repo
        self._todos = todos
        self._retros = retros

    async def _get(self, user_id: str, proposal_id: str) -> Proposal:
        proposal = await self._repo.find_by_id(proposal_id, user_id, for_update=True)
        if proposal is None:
            raise AiProposalNotFoundException()
        return proposal

    async def get(self, user_id: str, proposal_id: str) -> Proposal:
        proposal = await self._repo.find_by_id(proposal_id, user_id)
        if proposal is None:
            raise AiProposalNotFoundException()
        return proposal

    async def list_by_conversation(self, conversation_id: str) -> list[Proposal]:
        return await self._repo.list_by_conversation(conversation_id)

    async def apply(self, user_id: str, proposal_id: str, item_keys: list[str] | None) -> Proposal:
        proposal = await self._get(user_id, proposal_id)
        if proposal.status == "applied":
            raise AiProposalAlreadyAppliedException()
        if proposal.status != "pending":
            raise AiProposalStateInvalidException(f"Proposal is {proposal.status}.")
        items = proposal.items
        if item_keys is not None:
            unknown = set(item_keys) - {i["key"] for i in items}
            if unknown:
                raise AiProposalItemsInvalidException(f"Unknown items: {sorted(unknown)}")
            items = [i for i in items if i["key"] in item_keys]
        if not items:
            raise AiProposalItemsInvalidException("No items selected.")

        if proposal.kind == "move":
            stale = []
            for item in items:
                todo = await self._todos.get(user_id, item["todoId"])
                if todo is None or not _matches(todo, item["before"]):
                    stale.append({"key": item["key"], "todoId": item["todoId"]})
            if stale:
                raise AiProposalStaleException("Todos changed since the proposal.", details=stale)

        applied: dict[str, Any] = {}
        for item in items:
            after = item["after"]
            if proposal.kind == "add":
                todo_id = await self._todos.create(
                    user_id,
                    item["title"],
                    after["date_key"],
                    _dt(after.get("start_time")),
                    _dt(after.get("end_time")),
                    after.get("timezone"),
                )
                applied[item["key"]] = {"todo_id": todo_id, "created": True, "after": after}
            elif proposal.kind == "move":
                previous = {k: item["before"].get(k) for k in after if k != "timezone"}
                if "start_time" in after:
                    current = await self._todos.get(user_id, item["todoId"])
                    previous["timezone"] = current.timezone if current else None
                result_id = await self._todos.apply_patch(user_id, item["todoId"], after)
                applied[item["key"]] = {
                    "todo_id": result_id,
                    "created": False,
                    "previous": previous,
                    "after": after,
                }
            else:  # retro_draft
                entry_id = await self._retros.create_draft(
                    user_id, after["date_key"], after["content"]
                )
                applied[item["key"]] = {
                    "entry_id": entry_id,
                    "created": True,
                    "content": after["content"],
                }

        now = datetime.now(UTC)
        return await self._repo.save(
            replace(proposal, status="applied", applied=applied, applied_at=now, updated_at=now)
        )

    async def undo(self, user_id: str, proposal_id: str) -> UndoResult:
        proposal = await self._get(user_id, proposal_id)
        if proposal.status != "applied" or not proposal.applied:
            raise AiProposalStateInvalidException("Proposal is not applied.")
        titles = {i["key"]: i["title"] for i in proposal.items}
        skipped: list[str] = []
        for key, record in proposal.applied.items():
            if "entry_id" in record:
                entry = await self._retros.get(user_id, record["entry_id"])
                # 적용 뒤 사용자가 고쳤거나 지운 회고는 건드리지 않는다 — 편집을 잃지 않게.
                if entry is None or entry.get("content") != record.get("content"):
                    skipped.append(key)
                else:
                    await self._retros.delete(user_id, record["entry_id"])
                continue
            todo = await self._todos.get(user_id, record["todo_id"])
            after = {k: v for k, v in record["after"].items() if k != "timezone"}
            if (
                todo is None
                or not _matches(todo, after)
                or (record["created"] and todo.title != titles.get(key))
            ):
                skipped.append(key)  # 적용 뒤 사용자가 고쳤거나 지웠다 — 건드리지 않는다
                continue
            if record["created"]:
                await self._todos.delete(user_id, record["todo_id"])
            else:
                await self._todos.apply_patch(user_id, record["todo_id"], record["previous"])
        now = datetime.now(UTC)
        saved = await self._repo.save(replace(proposal, status="undone", updated_at=now))
        return UndoResult(saved, skipped)

    async def dismiss(self, user_id: str, proposal_id: str) -> Proposal:
        proposal = await self._get(user_id, proposal_id)
        if proposal.status != "pending":
            raise AiProposalStateInvalidException(f"Proposal is {proposal.status}.")
        return await self._repo.save(
            replace(proposal, status="dismissed", updated_at=datetime.now(UTC))
        )


def _dt(value: Any) -> datetime | None:
    return datetime.fromisoformat(value) if isinstance(value, str) else None
