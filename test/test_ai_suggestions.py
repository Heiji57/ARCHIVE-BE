"""AI 추천(5a, 규칙 기반) — 규칙(순수)과 실제 DB 위 흐름(추천 → 적용 → 되돌리기 → 넘기기).

- 빈 칸: 일하는 시간 안에서 시간 있는 할 일과 겹치지 않는 기본 길이 칸. 찾은 칸끼리도 겹치지 않는다.
- 지난 마감: 오늘로/내일로. 마감이 따로 있으면 함께 옮긴다(due >= date 제약).
- 커밋과 맞는 일: 제목 낱말 둘 이상이 한 커밋 메시지에.
- 적용은 할 일 수정 규칙으로, 되돌리기는 바뀐 필드의 이전 값으로. 넘긴 추천은 다시 안 나온다.
"""

import os
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.shared.infrastructure.database.models  # noqa: F401  (FK 대상 테이블 등록)
from app.ai.application.use_cases.suggestions import (
    ApplySuggestionUseCase,
    DismissSuggestionUseCase,
    GetSuggestionsUseCase,
    SuggestionService,
    UndoSuggestionUseCase,
)
from app.ai.application.use_cases.usage import AiUsageService
from app.ai.domain.exceptions.exceptions import (
    AiSuggestionActionInvalidException,
    AiUsageLimitExceededException,
)
from app.ai.domain.models.snapshots import TodoSnapshot
from app.ai.domain.services.suggestion_rules import (
    commit_match_suggestions,
    find_free_slots,
    overdue_suggestions,
    texts,
)
from app.ai.infrastructure.adapters.todo_adapter import TodoAdapter
from app.ai.infrastructure.persistence.repositories.suggestion_repo import (
    AiUsageRepository,
    SuggestionRepository,
)
from app.settings.infrastructure.persistence.repositories.user_settings_repo import (
    UserSettingsRepository,
)
from app.todo.application.use_cases.batch_update_todos import BatchUpdateTodosUseCase
from app.todo.application.use_cases.update_todo import UpdateTodoUseCase
from app.todo.infrastructure.persistence.repositories.todo_repo import TodoRepository
from app.user.infrastructure.persistence.repositories.user_repo import UserRepository

_SEOUL = ZoneInfo("Asia/Seoul")
_T = texts("ko")


def _at(h, m=0, d=16):
    return datetime(2026, 11, d, h, m, tzinfo=_SEOUL)


# ── 규칙 ────────────────────────────────────────────────────────────────────


def test_free_slots_skip_busy_and_each_other():
    busy = [(_at(9), _at(10)), (_at(10, 30), _at(11))]
    slots = find_free_slots(_at(9), _at(12), busy, timedelta(minutes=30), count=3)
    assert slots == [(_at(10), _at(10, 30)), (_at(11), _at(11, 30)), (_at(11, 30), _at(12))]


def test_free_slots_start_after_now_rounded_to_quarter():
    slots = find_free_slots(_at(9), _at(18), [], timedelta(hours=1), 1, not_before=_at(13, 7))
    assert slots == [(_at(13, 15), _at(14, 15))]


def test_free_slots_none_when_day_full():
    assert find_free_slots(_at(9), _at(10), [(_at(9), _at(10))], timedelta(minutes=30), 2) == []


def test_overdue_moves_due_date_too():
    todo = TodoSnapshot(
        id="t1",
        title="보고서",
        date_key="2026-11-10",
        status="not-start",
        due_date_key="2026-11-12",
    )
    (c,) = overdue_suggestions([todo], date(2026, 11, 16), _T)
    assert c.reason == "11/12 마감이 지났어요"
    assert [a.patch for a in c.actions] == [
        {"date_key": "2026-11-16", "due_date_key": "2026-11-16"},
        {"date_key": "2026-11-17", "due_date_key": "2026-11-17"},
    ]


def test_commit_match():
    open_todo = TodoSnapshot(
        id="t", title="경계 주 깜빡임 고치기", date_key="2026-11-16", status="not-start"
    )
    done = TodoSnapshot(id="d", title="경계 주 깜빡임", date_key="2026-11-16", status="done")
    other = TodoSnapshot(id="o", title="장보기", date_key="2026-11-16", status="not-start")
    got = commit_match_suggestions(
        [open_todo, done, other], ["fix: 경계 주 스크롤 깜빡임 해결"], _T
    )
    assert [(c.todo_id, c.actions[0].patch) for c in got] == [("t", {"status": "done"})]


# ── DB 흐름 ─────────────────────────────────────────────────────────────────

_TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://ADMIN:heijiADMIN20090220!@localhost:5437/archive",
)
_USER = "usr_redesign_ai"


class _NoCommits:
    async def messages_on(self, user_id, day):
        return []


class _Queue:
    async def enqueue(self, *a):
        pass


@pytest.fixture
async def factory():
    engine = create_async_engine(_TEST_DB_URL)
    f = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with f.begin() as s:
            if await s.scalar(text("SELECT to_regclass('public.ai_suggestions')")) is None:
                pytest.skip("TEST_DATABASE_URL 의 DB 가 최신 마이그레이션이 아니다")
    except OSError:
        pytest.skip("test DB unavailable")
    async with f.begin() as s:
        await s.execute(text("DELETE FROM users WHERE id = :id"), {"id": _USER})
        await s.execute(
            text(
                "INSERT INTO users (id, email, created_at, country, timezone)"
                " VALUES (:id, 'ai@example.invalid', now(), 'KR', 'Asia/Seoul')"
            ),
            {"id": _USER},
        )
        await s.execute(
            text(
                "INSERT INTO todos (id, user_id, title, status, date_key, created_at, tags)"
                " VALUES"
                " ('todo_ai_late', :u, '지난 보고서', 'not-start', '2026-11-10', now(), '{}'),"
                " ('todo_ai_free', :u, '시간 없는 일', 'not-start', '2026-11-16', now(), '{}')"
            ),
            {"u": _USER},
        )
    yield f
    async with f.begin() as s:
        await s.execute(text("DELETE FROM users WHERE id = :id"), {"id": _USER})
    await engine.dispose()


def _svc(session) -> SuggestionService:
    todo_repo = TodoRepository(session)
    batch = BatchUpdateTodosUseCase(todo_repo, UpdateTodoUseCase(todo_repo))
    return SuggestionService(
        SuggestionRepository(session),
        TodoAdapter(todo_repo, batch, _Queue(), None, None, None),  # type: ignore[arg-type]
        _NoCommits(),
        UserSettingsRepository(session),
        UserRepository(session),
    )


_NOW = datetime(2026, 11, 16, 1, 0, tzinfo=UTC)  # KST 10:00 월요일


async def test_suggest_apply_undo_dismiss(factory):
    day = date(2026, 11, 16)
    async with factory.begin() as s:
        got = await GetSuggestionsUseCase(_svc(s)).execute(_USER, day, now=_NOW)
        by_kind = {g.kind: g for g in got}
        assert set(by_kind) == {"overdue", "free_slot"}
        free = by_kind["free_slot"]
        assert datetime.fromisoformat(free.payload["slot"]["start"]) == _at(10)

        applied = await ApplySuggestionUseCase(_svc(s)).execute(_USER, by_kind["overdue"].id, 0)
        assert applied.status == "applied"
        moved = await TodoRepository(s).find_by_id("todo_ai_late", _USER)
        assert moved.date_key == "2026-11-16"

        with pytest.raises(AiSuggestionActionInvalidException):
            await ApplySuggestionUseCase(_svc(s)).execute(_USER, applied.id, 0)

        await UndoSuggestionUseCase(_svc(s)).execute(_USER, applied.id)
        assert (await TodoRepository(s).find_by_id("todo_ai_late", _USER)).date_key == "2026-11-10"

        await DismissSuggestionUseCase(_svc(s)).execute(_USER, free.id)

    async with factory.begin() as s:
        again = await GetSuggestionsUseCase(_svc(s)).execute(_USER, day, now=_NOW)
        # 넘긴 빈 칸 추천은 다시 안 나오고, 되돌린 지난 마감 추천은 다시 보인다
        assert {g.kind for g in again} == {"overdue"}
        assert again[0].id == by_kind["overdue"].id


async def test_usage_quota(factory):
    async with factory.begin() as s:
        usage = AiUsageService(AiUsageRepository(s), UserRepository(s), day_limit=2, month_limit=3)
        await usage.record(_USER, 10, 20, now=_NOW)
        await usage.record(_USER, 5, 5, now=_NOW)
        report = await usage.report(_USER, now=_NOW)
        assert (report.day_used, report.month_used) == (2, 2)
        with pytest.raises(AiUsageLimitExceededException) as ei:
            await usage.check(_USER, now=_NOW)
        assert ei.value.details == [{"scope": "day", "used": 2, "limit": 2}]
        # 다음 날은 하루 상한이 풀리지만 한 달 상한(3)이 남는다
        await usage.record(_USER, 1, 1, now=_NOW + timedelta(days=1))
        with pytest.raises(AiUsageLimitExceededException) as ei:
            await usage.check(_USER, now=_NOW + timedelta(days=2))
        assert ei.value.details[0]["scope"] == "month"


def test_usage_limit_maps_to_429_not_the_gemini_quota_503():
    from app.ai.domain.exceptions.exceptions import AiUsageLimitExceededException
    from app.shared.infrastructure.errors.handler import to_http_response

    assert to_http_response(AiUsageLimitExceededException()).status_code == 429


async def test_concurrent_first_get_creates_one_row_each(factory):
    import asyncio

    async def get():
        async with factory.begin() as s:
            return await GetSuggestionsUseCase(_svc(s)).execute(_USER, date(2026, 11, 16), now=_NOW)

    a, b = await asyncio.gather(get(), get())
    assert {x.id for x in a} == {x.id for x in b}


async def test_free_slot_in_the_past_is_not_applied(factory):
    day = date(2026, 11, 16)
    async with factory.begin() as s:
        got = await GetSuggestionsUseCase(_svc(s)).execute(_USER, day, now=_NOW)
        free = next(g for g in got if g.kind == "free_slot")
        with pytest.raises(AiSuggestionActionInvalidException):
            await ApplySuggestionUseCase(_svc(s)).execute(
                _USER, free.id, 0, now=_NOW + timedelta(hours=5)
            )
