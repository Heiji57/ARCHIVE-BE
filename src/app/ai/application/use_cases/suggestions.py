"""AI 추천(5a, 규칙 기반) — 계산·저장·적용·넘기기·되돌리기.

추천은 요청 때 계산해 저장하고, 같은 날 다시 부르면 상태를 이어 쓴다(넘긴 것은 다시 안 나옴).
적용은 할 일 수정 규칙을 그대로 타고, 바꾼 필드의 이전 값을 남겨 되돌릴 수 있게 한다.
추천은 LLM 을 부르지 않아 사용량에 세지 않는다.

행동 학습을 켜 두면(기본) 보임·적용·넘김·되돌림을 기록하고, 쌓인 통계로 순서·노출(받아들일
확률)·빈 칸 시각과 길이·버튼 순서를 정한다(`LearningService`, `suggestion_ranker`).
"""

from dataclasses import replace
from datetime import UTC, date, datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from app.ai.application.ports import CommitPort, TodoPort
from app.ai.application.services.learning import LearningService, event_context
from app.ai.domain.exceptions.exceptions import (
    AiSuggestionActionInvalidException,
    AiSuggestionNotFoundException,
)
from app.ai.domain.models.learning import BehaviorModel
from app.ai.domain.models.snapshots import TodoSnapshot
from app.ai.domain.models.suggestion import Suggestion, SuggestionCandidate
from app.ai.domain.repositories.repository import ISuggestionRepository
from app.ai.domain.services.suggestion_ranker import context_of, rank, seeded_rng
from app.ai.domain.services.suggestion_rules import (
    commit_match_suggestions,
    free_slot_suggestions,
    overdue_suggestions,
    texts,
)
from app.settings.domain.models.preferences import parse_hhmm
from app.settings.domain.models.user_settings import UserSettings
from app.settings.domain.repositories.repository import IUserSettingsRepository
from app.shared.domain.utils.id import generate_id
from app.user.domain.repositories.repository import IUserRepository

_KIND_ORDER = {"overdue": 0, "free_slot": 1, "commit_match": 2, "unscheduled_long": 3}


class SuggestionService:
    """추천 유스케이스들이 공유하는 의존성 묶음."""

    def __init__(
        self,
        repo: ISuggestionRepository,
        todos: TodoPort,
        commits: CommitPort,
        settings_repo: IUserSettingsRepository,
        user_repo: IUserRepository,
        learning: LearningService,
    ) -> None:
        self.repo = repo
        self.todos = todos
        self.commits = commits
        self.settings_repo = settings_repo
        self.user_repo = user_repo
        self.learning = learning

    async def context(self, user_id: str) -> tuple[UserSettings, ZoneInfo]:
        settings = await self.settings_repo.find_by_user_id(user_id) or UserSettings.default(
            user_id
        )
        user = await self.user_repo.find_by_id(user_id)
        return settings, ZoneInfo(user.timezone if user else "UTC")

    async def record(
        self,
        suggestion: Suggestion,
        type_: Literal["sugg_shown", "sugg_applied", "sugg_dismissed", "sugg_undone"],
        tz: ZoneInfo,
        now: datetime | None = None,
        **extra: Any,
    ) -> None:
        at = event_context(tz, now)
        await self.learning.record(
            suggestion.user_id,
            type_,
            at,
            {
                "suggestion_id": suggestion.id,
                "kind": suggestion.kind,
                "day": at.day,
                "ctx": at.ctx,
                "tag": suggestion.payload.get("tag"),
                **extra,
            },
            todo_id=suggestion.todo_id,
        )


class GetSuggestionsUseCase:
    def __init__(self, svc: SuggestionService) -> None:
        self._svc = svc

    async def execute(
        self, user_id: str, day: date, now: datetime | None = None
    ) -> list[Suggestion]:
        settings, tz = await self._svc.context(user_id)
        now = (now or datetime.now(UTC)).astimezone(tz)
        model = await self._svc.learning.model(user_id, now.date(), now.astimezone(UTC))
        candidates = await self._candidates(user_id, day, now, settings, tz, model)
        ranked = model is not None and model.can_rank
        if model is not None:
            ctx = context_of(now)
            candidates = rank(candidates, model, ctx, seeded_rng(user_id, day.isoformat(), ctx))
        order = {(c.kind, c.todo_id): i for i, c in enumerate(candidates)}

        existing = {
            (s.kind, s.todo_id): s
            for s in await self._svc.repo.list_for_date(user_id, day.isoformat())
        }
        shown: list[Suggestion] = []
        for c in candidates:
            prev = existing.get((c.kind, c.todo_id))
            if prev is not None and prev.status != "shown":
                continue  # 넘겼거나 이미 적용한 추천은 다시 내지 않는다
            payload = _payload(c)
            if prev is None:
                # 같은 날을 동시에 두 번 불러도 한 행 — 늦은 쪽은 먼저 들어간 행을 받는다.
                new_id = generate_id("sugg")
                saved = await self._svc.repo.insert_if_absent(
                    Suggestion(
                        id=new_id,
                        user_id=user_id,
                        date_key=day.isoformat(),
                        kind=c.kind,
                        todo_id=c.todo_id,
                        payload=payload,
                        created_at=datetime.now(UTC),
                    )
                )
                if saved.status != "shown":
                    continue
                if saved.id == new_id:
                    await self._svc.record(saved, "sugg_shown", tz, now)
            elif prev.payload != payload:
                saved = await self._svc.repo.save(
                    replace(prev, payload=payload, updated_at=datetime.now(UTC))
                )
            else:
                saved = prev
            shown.append(saved)
        if ranked:
            shown.sort(key=lambda s: order.get((s.kind, s.todo_id), 99))
        else:
            shown.sort(key=lambda s: _KIND_ORDER.get(s.kind, 9))
        return shown

    async def _candidates(
        self,
        user_id: str,
        day: date,
        now: datetime,
        settings: UserSettings,
        tz: ZoneInfo,
        model: BehaviorModel | None,
    ) -> list[SuggestionCandidate]:
        t = texts(settings.locale)
        todos = await self._svc.todos.list_on(user_id, day.isoformat())
        out: list[SuggestionCandidate] = []
        if day == now.date():
            overdue = await self._svc.todos.list_overdue(
                user_id, str(tz), limit=20, today=day.isoformat()
            )
            out += overdue_suggestions(overdue, day, t, model.deferrals if model else None)

        hours = settings.work_schedule.hours_on(day)
        if hours is not None and day >= now.date():
            work_start = datetime.combine(day, parse_hhmm(hours.start), tz)
            work_end = datetime.combine(day, parse_hhmm(hours.end), tz)
            out += free_slot_suggestions(
                todos,
                work_start,
                work_end,
                settings.default_todo_minutes,
                str(tz),
                t,
                now=now if day == now.date() else None,
                model=model,
            )

        messages = await self._svc.commits.messages_on(user_id, day)
        if messages:
            out += commit_match_suggestions(todos, messages, t)
        # 같은 할 일에 여러 종류가 겹치면 앞 종류(지난 마감 > 빈 칸 > 커밋)만 남긴다.
        seen: set[str] = set()
        unique: list[SuggestionCandidate] = []
        for c in out:
            if c.todo_id not in seen:
                seen.add(c.todo_id)
                unique.append(c)
        return unique


class ApplySuggestionUseCase:
    def __init__(self, svc: SuggestionService) -> None:
        self._svc = svc

    async def execute(
        self, user_id: str, suggestion_id: str, action_index: int, now: datetime | None = None
    ) -> Suggestion:
        suggestion = await _get(self._svc.repo, user_id, suggestion_id)
        if suggestion.status != "shown":
            raise AiSuggestionActionInvalidException("Suggestion is not open.")
        actions = suggestion.actions
        if not 0 <= action_index < len(actions):
            raise AiSuggestionActionInvalidException("Unknown action.")
        action = actions[action_index]
        patch = action.patch

        current = await self._svc.todos.get(user_id, suggestion.todo_id)
        if current is None:
            raise AiSuggestionNotFoundException("The todo no longer exists.")
        if suggestion.kind == "free_slot":
            await self._check_slot_still_free(user_id, suggestion, now or datetime.now(UTC))
        applied: dict[str, Any]
        if action.code == "drop":
            # 내려놓기 — 휴지통으로(30일 안에 되살릴 수 있다). 반복 회차는 규칙이 이 버튼을 안 만든다.
            if current.recurring:
                raise AiSuggestionActionInvalidException("Recurring todos cannot be dropped.")
            await self._svc.todos.delete(user_id, suggestion.todo_id)
            applied = {"todo_id": suggestion.todo_id, "previous": {}, "dropped": True}
        else:
            previous = _previous_values(current, patch)
            result_id = await self._svc.todos.apply_patch(user_id, suggestion.todo_id, patch)
            applied = {"todo_id": result_id, "previous": previous}
        saved = await self._svc.repo.save(
            replace(
                suggestion,
                status="applied",
                applied={**applied, "action_index": action_index},
                updated_at=datetime.now(UTC),
            )
        )
        _, tz = await self._svc.context(user_id)
        await self._svc.record(
            saved, "sugg_applied", tz, now, action=action.code, todo_id=applied["todo_id"]
        )
        return saved

    async def _check_slot_still_free(
        self, user_id: str, suggestion: Suggestion, now: datetime
    ) -> None:
        """추천을 만든 뒤 지나갔거나 다른 일이 들어온 칸이면 적용하지 않는다.

        다시 불러 새 칸을 받게 한다.
        """
        slot = suggestion.payload.get("slot") or {}
        start, end = datetime.fromisoformat(slot["start"]), datetime.fromisoformat(slot["end"])
        if start < now:
            raise AiSuggestionActionInvalidException("The slot has passed.")
        todos = await self._svc.todos.list_on(user_id, suggestion.date_key)
        if any(
            t.is_timed and t.id != suggestion.todo_id and t.start_time < end and start < t.end_time  # type: ignore[operator]
            for t in todos
        ):
            raise AiSuggestionActionInvalidException("The slot is no longer free.")


class UndoSuggestionUseCase:
    def __init__(self, svc: SuggestionService) -> None:
        self._svc = svc

    async def execute(self, user_id: str, suggestion_id: str) -> Suggestion:
        """적용한 것을 이전 값으로 되돌리고 추천을 다시 보이게 한다."""
        suggestion = await _get(self._svc.repo, user_id, suggestion_id)
        if suggestion.status != "applied" or not suggestion.applied:
            raise AiSuggestionActionInvalidException("Suggestion is not applied.")
        if suggestion.applied.get("dropped"):
            if not await self._svc.todos.restore(user_id, suggestion.applied["todo_id"]):
                raise AiSuggestionNotFoundException("The todo is no longer in the trash.")
        else:
            await self._svc.todos.apply_patch(
                user_id,
                suggestion.applied["todo_id"],
                suggestion.applied["previous"],
                observe=False,  # 되돌림은 sugg_undone 으로만 남긴다
            )
        saved = await self._svc.repo.save(
            replace(suggestion, status="shown", applied=None, updated_at=datetime.now(UTC))
        )
        _, tz = await self._svc.context(user_id)
        await self._svc.record(saved, "sugg_undone", tz)
        return saved


class DismissSuggestionUseCase:
    def __init__(self, svc: SuggestionService) -> None:
        self._svc = svc

    async def execute(
        self, user_id: str, suggestion_id: str, reason: str | None = None
    ) -> Suggestion:
        """넘기기 — 같은 날 같은 (종류, 할 일) 추천은 다시 나오지 않는다.

        reason(not_now | not_needed | wrong_time)은 학습 무게만 바꾼다(필요 없음이 가장 무겁다).
        """
        suggestion = await _get(self._svc.repo, user_id, suggestion_id)
        if suggestion.status == "applied":
            raise AiSuggestionActionInvalidException("Undo before dismissing.")
        if suggestion.status == "dismissed":
            return suggestion  # 두 번 눌러도 한 번만 기록
        saved = await self._svc.repo.save(
            replace(suggestion, status="dismissed", updated_at=datetime.now(UTC))
        )
        _, tz = await self._svc.context(user_id)
        await self._svc.record(saved, "sugg_dismissed", tz, reason=reason)
        return saved


async def _get(repo: ISuggestionRepository, user_id: str, suggestion_id: str) -> Suggestion:
    # 행을 잠근다 — 적용·되돌리기·넘기기를 동시에 두 번 눌러도 상태 판정이 한 번씩만 통과한다.
    suggestion = await repo.find_by_id(suggestion_id, user_id, for_update=True)
    if suggestion is None:
        raise AiSuggestionNotFoundException()
    return suggestion


def _payload(c: SuggestionCandidate) -> dict[str, Any]:
    return {
        "title": c.title,
        "reason": c.reason,
        "reason_code": c.reason_code,
        "learned": c.learned,
        "tag": c.tag,
        "slot": (
            {"start": c.slot[0].isoformat(), "end": c.slot[1].isoformat()} if c.slot else None
        ),
        "actions": [{"label": a.label, "patch": a.patch, "code": a.code} for a in c.actions],
    }


def _previous_values(todo: TodoSnapshot, patch: dict[str, Any]) -> dict[str, Any]:
    """patch 가 바꾸는 필드의 지금 값 — 되돌리기는 이 값을 같은 규칙으로 다시 쓴다."""

    def iso(v: datetime | None) -> str | None:
        return v.isoformat() if v else None

    current = {
        "date_key": todo.date_key,
        "due_date_key": todo.due_date_key,
        "status": todo.status,
        "start_time": iso(todo.start_time),
        "end_time": iso(todo.end_time),
        "timezone": todo.timezone,
    }
    return {k: current[k] for k in patch if k in current}
