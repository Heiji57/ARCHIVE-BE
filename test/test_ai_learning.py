"""AI 행동 학습 — 기록 → 통계 → 추천 순서·빈 칸·길이·내려놓기.

순수 함수(통계 계산, 톰슨 샘플링 순위, 빈 칸 고르기)와 실제 DB 위 흐름(추천 보임·적용·넘김 기록,
할 일 수정 알림, 내려놓기 → 되돌리면 되살림, 학습 끄기·지우기, 효과 지표)을 본다.
"""

import os
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_ai_suggestions import _svc  # 같은 배선(학습 포함)을 쓴다

import app.shared.infrastructure.database.models  # noqa: F401  (FK 대상 테이블 등록)
from app.ai.application.services.learning import LearningService, event_context
from app.ai.application.use_cases.ai_settings import AiSettingsUseCase
from app.ai.application.use_cases.suggestions import (
    ApplySuggestionUseCase,
    DismissSuggestionUseCase,
    GetSuggestionsUseCase,
    UndoSuggestionUseCase,
)
from app.ai.domain.exceptions.exceptions import (
    AiSuggestionActionInvalidException,
    AiSuggestionNotFoundException,
)
from app.ai.domain.models.learning import (
    MIN_EVENTS_TO_RANK,
    Arm,
    BehaviorEvent,
    BehaviorModel,
)
from app.ai.domain.models.snapshots import TodoSnapshot
from app.ai.domain.models.suggestion import SuggestionAction, SuggestionCandidate
from app.ai.domain.services.behavior_model import build_model
from app.ai.domain.services.suggestion_ranker import (
    context_of,
    estimate_minutes,
    hour_profile,
    rank,
    rank_seed,
)
from app.ai.domain.services.suggestion_rules import (
    find_free_slots,
    free_slot_suggestions,
    overdue_suggestions,
    texts,
)
from app.ai.infrastructure.persistence.repositories.ai_settings_repo import AiSettingsRepository
from app.ai.infrastructure.persistence.repositories.learning_repo import BehaviorRepository
from app.todo.infrastructure.persistence.repositories.todo_repo import TodoRepository

_SEOUL = ZoneInfo("Asia/Seoul")
_T = texts("ko")
_NOW = datetime(2026, 11, 16, 1, 0, tzinfo=UTC)  # KST 10:00 월요일
_TODAY = date(2026, 11, 16)


def _ev(type_, days_ago=0.0, tid=None, **data):
    """tid = 이벤트의 할 일 id. data 의 todo_id(적용 결과 할 일)와 따로."""
    return BehaviorEvent(
        type=type_, created_at=_NOW - timedelta(days=days_ago), todo_id=tid, data=data
    )


_CTX = {"wk": "weekday", "dp": "morning"}


# ── 통계 ──────────────────────────────────────────────────────────────────────


def test_rewards_and_decay():
    events = [
        _ev("sugg_shown", suggestion_id="s1", kind="overdue", day="2026-11-16", ctx=_CTX),
        _ev("sugg_applied", suggestion_id="s1", kind="overdue", action="to_tomorrow",
            todo_id="t1", day="2026-11-16", ctx=_CTX),
        _ev("todo_done", -0.01, tid="t1", hour=10, day="2026-11-16"),  # 적용 뒤 그날 끝냄 → +1 더
        _ev("sugg_dismissed", 30, suggestion_id="s2", kind="free_slot", reason="not_needed",
            day="2026-10-17", ctx=_CTX),
        _ev("sugg_shown", 2, suggestion_id="s3", kind="commit_match", day="2026-11-14", ctx=_CTX),
        _ev("sugg_shown", suggestion_id="s4", kind="commit_match", day="2026-11-16", ctx=_CTX),
    ]
    m = build_model(events, _NOW, _TODAY)
    assert m.accept["overdue"].pos == pytest.approx(2.0)
    assert m.actions["overdue"] == {"to_tomorrow": pytest.approx(1.0)}
    # 30일 전 '필요 없음' 넘김 = 1 × 반감
    assert m.accept["free_slot|weekday|morning"].neg == pytest.approx(0.5, rel=1e-3)
    # 그저께 보이고 반응 없음 → 무시(0.1 × 감쇠). 오늘 보인 것은 아직 무시가 아니다.
    assert m.accept["commit_match"].neg == pytest.approx(0.1 * 0.5 ** (2 / 30), rel=1e-3)
    assert m.reactions == 2


def test_mark_done_apply_is_not_done_after_apply():
    """'끝냄으로' 는 적용하면서 끝낸다 — 끝냄 기록이 같은 요청에서 먼저 남아도 보너스가 아니다."""
    events = [
        _ev("todo_done", tid="t1", hour=10, day="2026-11-16"),
        _ev("sugg_applied", suggestion_id="s1", kind="commit_match", action="mark_done",
            todo_id="t1", day="2026-11-16", ctx=_CTX),
    ]
    assert build_model(events, _NOW, _TODAY).accept["commit_match"].pos == pytest.approx(1.0)


def test_undo_cancels_apply_and_counts_against():
    events = [
        _ev("sugg_applied", suggestion_id="s1", kind="free_slot", action="schedule",
            todo_id="t1", day="2026-11-16", ctx=_CTX),
        _ev("sugg_undone", suggestion_id="s1", kind="free_slot", day="2026-11-16", ctx=_CTX),
    ]
    arm = build_model(events, _NOW, _TODAY).accept["free_slot"]
    assert (arm.pos, arm.neg) == (pytest.approx(0.0), pytest.approx(1.0))


def test_hours_minutes_and_deferrals():
    events = [
        _ev("todo_done", tid="a", hour=15, minutes=60, tag="공부"),
        _ev("todo_retimed", tid="b", hour=15, minutes=90, tag="공부"),
        _ev("todo_moved", tid="c", **{"from": "2026-11-10", "to": "2026-11-12"}),
        _ev("todo_moved", tid="c", **{"from": "2026-11-12", "to": "2026-11-14"}),
        _ev("todo_moved", tid="c", **{"from": "2026-11-14", "to": "2026-11-13"}),  # 앞당김
        _ev("todo_moved", 40, tid="d", **{"from": "2026-10-01", "to": "2026-10-02"}),  # 오래됨
    ]
    m = build_model(events, _NOW, _TODAY)
    assert m.hours["공부"][15] == pytest.approx(3.0)  # 끝냄 1 + 시간 정함 2
    assert m.hours["*"][15] == pytest.approx(3.0)
    assert m.minutes["공부"] == [60, 90]
    assert m.deferrals == {"c": 2}


def test_model_json_round_trip():
    m = build_model(
        [_ev("todo_done", tid="a", hour=9, minutes=30, tag="x")], _NOW, _TODAY
    )
    m.accept["overdue"] = Arm(1.5, 0.25)
    again = BehaviorModel.from_json(m.to_json())
    assert again.to_json() == m.to_json()


# ── 순위(A) ───────────────────────────────────────────────────────────────────


def _cand(kind, todo_id, urgency=1.0):
    return SuggestionCandidate(
        kind=kind, todo_id=todo_id, title=todo_id, reason="", urgency=urgency,
        actions=(SuggestionAction("a", {}, "to_today"), SuggestionAction("b", {}, "to_tomorrow")),
    )


def test_rank_waits_for_enough_reactions():
    m = BehaviorModel(accept={"overdue": Arm(0, 50)}, reactions=MIN_EVENTS_TO_RANK - 1)
    got = rank([_cand("overdue", "t1")], m, _CTX, rank_seed("u", "d", _CTX))
    assert [c.todo_id for c in got] == ["t1"] and not got[0].learned


def test_rank_hides_mostly_dismissed_kind_and_is_stable():
    m = BehaviorModel(
        accept={"commit_match": Arm(0, 40), "overdue": Arm(30, 2)},
        actions={"overdue": {"to_tomorrow": 5.0}},
        reactions=72,
    )
    cands = [_cand("commit_match", "c1"), _cand("overdue", "o1")]
    first = rank(cands, m, _CTX, rank_seed("u", "2026-11-16", _CTX))
    again = rank(cands, m, _CTX, rank_seed("u", "2026-11-16", _CTX))
    assert [c.todo_id for c in first] == [c.todo_id for c in again]  # 같은 날·시간대면 같은 순서
    assert first[0].todo_id == "o1" and first[0].learned
    assert [a.code for a in first[0].actions] == ["to_tomorrow", "to_today"]  # 자주 누른 버튼 앞
    # 거의 다 넘긴 종류도 가끔은 보인다(탐색) — 그러나 대부분 숨는다
    shown = sum(
        any(c.todo_id == "c1" for c in rank(cands, m, _CTX, rank_seed("u", f"d{i}", _CTX)))
        for i in range(200)
    )
    assert 0 < shown < 60


def test_rank_draw_does_not_depend_on_other_candidates():
    """다른 후보가 빠져도(적용·넘김) 남은 후보의 노출·뽑힌 값은 같다."""
    m = BehaviorModel(accept={"overdue": Arm(3, 3)}, reactions=72)
    cands = [_cand("overdue", f"o{i}") for i in range(6)]
    for d in range(30):
        seed = rank_seed("u", f"d{d}", _CTX)
        full = [c.todo_id for c in rank(cands, m, _CTX, seed)]
        rest = [c.todo_id for c in rank(cands[1:], m, _CTX, seed)]
        assert rest == [t for t in full if t != "o0"]


def test_hidden_suggestion_is_not_ignored_until_shown_again():
    def vis(type_, hours, sid):
        return _ev(type_, 1 + hours / 24, suggestion_id=sid, kind="free_slot",
                   day="2026-11-15", ctx=_CTX)

    events = [
        vis("sugg_shown", 3, "s1"), vis("sugg_hidden", 2, "s1"),  # 숨긴 채 끝남 → 무시 아님
        vis("sugg_shown", 3, "s2"),  # 보인 채 끝남 → 무시
        # 숨겼다 다시 보였는데 반응 없음 → 무시(한 번만)
        vis("sugg_shown", 3, "s3"), vis("sugg_hidden", 2, "s3"), vis("sugg_shown", 1, "s3"),
    ]
    arm = build_model(events, _NOW, _TODAY).accept["free_slot"]
    assert arm.neg == pytest.approx(0.2 * 0.5 ** (1 / 30), rel=2e-3)  # s2, s3


def test_moves_made_by_applying_are_not_deferrals():
    events = [
        _ev("todo_moved", 2, tid="t1", source="suggestion:s1",
            **{"from": "2026-11-10", "to": "2026-11-14"}),
        _ev("todo_moved", 1, tid="t1", source="proposal:p1",
            **{"from": "2026-11-14", "to": "2026-11-15"}),
        _ev("todo_moved", 1, tid="t1", **{"from": "2026-11-15", "to": "2026-11-16"}),  # 직접
    ]
    assert build_model(events, _NOW, _TODAY).deferrals == {"t1": 1}


class _FakeBehaviorRepo:
    def __init__(self):
        self.events = []

    async def add_event(self, user_id, event, mark_stale=True):
        self.events.append(event)


class _NoSettings:
    async def find(self, user_id):
        return None


async def test_moving_timed_todo_to_another_day_is_not_retimed():
    repo = _FakeBehaviorRepo()
    svc = LearningService(repo, _NoSettings())  # type: ignore[arg-type]
    at = event_context(_SEOUL, _NOW)

    def timed(day, hour):
        start = datetime(2026, 11, day, hour, tzinfo=_SEOUL)
        return TodoSnapshot(id="t1", title="x", date_key=f"2026-11-{day}", status="not-start",
                            start_time=start, end_time=start + timedelta(hours=1))

    await svc.todo_changed("u", timed(16, 15), timed(17, 15), at)  # 날짜만 옮김(시각 그대로)
    assert [e.type for e in repo.events] == ["todo_moved"]
    await svc.todo_changed("u", timed(17, 15), timed(17, 10), at)  # 시각을 바꿈
    assert [e.type for e in repo.events] == ["todo_moved", "todo_retimed"]


# ── 빈 칸(B)·길이(C) ──────────────────────────────────────────────────────────


def _at(h, m=0):
    return datetime(2026, 11, 16, h, m, tzinfo=_SEOUL)


def test_free_slot_without_model_is_unchanged():
    todos = [TodoSnapshot(id=f"t{i}", title="x", date_key="2026-11-16", status="not-start")
             for i in range(3)]
    got = free_slot_suggestions(todos, _at(9), _at(18), 60, "Asia/Seoul", _T)
    expected = find_free_slots(_at(9).astimezone(UTC), _at(18).astimezone(UTC), [],
                               timedelta(minutes=60), 3)
    assert [c.slot for c in got] == expected
    assert all(c.reason_code == "free_slot" and not c.learned for c in got)


def test_free_slot_prefers_usual_hour_and_learned_length():
    hours = [0.0] * 24
    hours[14] = 10.0
    model = BehaviorModel(
        hours={"*": hours, "공부": hours}, minutes={"*": [45] * 4, "공부": [45] * 4}
    )
    todo = TodoSnapshot(id="t1", title="x", date_key="2026-11-16", status="not-start",
                        tags=("공부",))
    [got] = free_slot_suggestions([todo], _at(9), _at(18), 60, "Asia/Seoul", _T, model=model)
    assert got.slot[0].astimezone(_SEOUL) == _at(14)
    # 전체 (4×45 + 3×60) / 7 ≈ 51.4, 태그 (4×45 + 3×51.4) / 7 ≈ 47.8 → 45
    assert got.reason_code == "free_slot_usual_time" and got.learned
    assert got.reason == "평소 14시쯤 하던 일이에요 · 보통 45분 걸렸어요"


def test_estimate_minutes_shrinks_toward_default():
    assert estimate_minutes(BehaviorModel(), "x", 50) == (50, False)
    # 전체 기록이 3건 미만이면 기본값 그대로(1~2건으로 칸 길이를 바꾸지 않는다)
    assert estimate_minutes(BehaviorModel(minutes={"*": [120]}), None, 60) == (60, False)
    assert estimate_minutes(BehaviorModel(minutes={"*": [15]}), None, 60) == (60, False)


def test_estimate_minutes_keeps_unusual_default():
    # 기본 20분이고 늘 20분 — 15분 단위로 맞춰도 같으니 기본값 그대로("보통 15분" 아님)
    assert estimate_minutes(BehaviorModel(minutes={"*": [20] * 5}), None, 20) == (20, False)
    # 긴 기본값은 240분으로 자르지 않는다
    assert estimate_minutes(BehaviorModel(minutes={"*": [480] * 5}), None, 480) == (480, False)
    assert estimate_minutes(BehaviorModel(minutes={"*": [420] * 9}), None, 480) == (435, True)


def test_estimate_minutes_learned_with_few_tag_samples():
    """태그 기록이 1건이어도 전체 기록이 충분하고 길이가 기본값과 다르면 학습값이다."""
    m = BehaviorModel(minutes={"*": [30, 30, 30, 90], "work": [90]})
    minutes, learned = estimate_minutes(m, "work", 30)
    assert minutes != 30 and learned
    # 추정이 기본값과 같으면 "보통 N분" 이라 할 것이 없다
    assert estimate_minutes(BehaviorModel(minutes={"*": [30] * 5}), None, 30) == (30, False)


def test_hour_profile_one_tag_event_keeps_global_evidence():
    glob = [0.0] * 24
    glob[9] = 40.0
    work = [0.0] * 24
    work[15] = 1.0
    profile = hour_profile(BehaviorModel(hours={"*": glob, "work": work}), "work")
    assert profile is not None  # 태그 1건 때문에 학습한 시간대를 끄지 않는다
    probs, _ = profile
    assert max(range(24), key=lambda h: probs[h]) == 9  # 전체 쪽으로 당겨져 있다


# ── 미룸(D) ───────────────────────────────────────────────────────────────────


def test_deferred_overdue_offers_drop_first_except_recurring():
    late = TodoSnapshot(id="t1", title="x", date_key="2026-11-10", status="not-start")
    series = TodoSnapshot(id="b::2026-11-10", title="y", date_key="2026-11-10",
                          status="not-start", recurring=True)
    got = overdue_suggestions([late, series], _TODAY, _T, {"t1": 3, "b::2026-11-10": 3})
    assert [a.code for a in got[0].actions] == ["drop", "to_today", "to_tomorrow"]
    assert (got[0].reason, got[0].reason_code) == ("3번 미룬 일이에요", "overdue_deferred")
    assert [a.code for a in got[1].actions] == ["to_today", "to_tomorrow"]
    assert got[0].urgency == pytest.approx(1 + 6 / 14)


def test_context_of():
    assert context_of(datetime(2026, 11, 21, 19, tzinfo=_SEOUL)) == {
        "wk": "weekend",
        "dp": "evening",
    }


# ── DB 흐름 ───────────────────────────────────────────────────────────────────

_TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://archive:archive@localhost:5432/archive_test"
)
_USER = "usr_ai_learning"


@pytest.fixture
async def factory():
    engine = create_async_engine(_TEST_DB_URL)
    f = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with f.begin() as s:
            if await s.scalar(text("SELECT to_regclass('public.ai_behavior_events')")) is None:
                pytest.skip("TEST_DATABASE_URL 의 DB 가 최신 마이그레이션이 아니다")
    except OSError:
        pytest.skip("test DB unavailable")
    async with f.begin() as s:
        await s.execute(text("DELETE FROM users WHERE id = :id"), {"id": _USER})
        await s.execute(
            text(
                "INSERT INTO users (id, email, created_at, country, timezone)"
                " VALUES (:id, 'learn@example.invalid', now(), 'KR', 'Asia/Seoul')"
            ),
            {"id": _USER},
        )
        await s.execute(
            text(
                "INSERT INTO todos (id, user_id, title, status, date_key, created_at, tags)"
                " VALUES"
                " ('todo_lr_late', :u, '미룬 보고서', 'not-start', '2026-11-10', now(), '{}'),"
                " ('todo_lr_free', :u, '시간 없는 일', 'not-start', '2026-11-16', now(), '{공부}')"
            ),
            {"u": _USER},
        )
    yield f
    async with f.begin() as s:
        await s.execute(text("DELETE FROM users WHERE id = :id"), {"id": _USER})
    await engine.dispose()


async def _events(s) -> list[tuple[str, str | None]]:
    rows = await s.execute(
        text(
            "SELECT type, todo_id FROM ai_behavior_events WHERE user_id = :u"
            " ORDER BY created_at, id"
        ),
        {"u": _USER},
    )
    return [(r[0], r[1]) for r in rows]


async def test_records_reactions_and_todo_changes(factory):
    async with factory.begin() as s:
        got = await GetSuggestionsUseCase(_svc(s)).execute(_USER, _TODAY, now=_NOW)
        by_kind = {g.kind: g for g in got}
        assert by_kind["overdue"].payload["reason_code"] == "overdue"
        assert [a["code"] for a in by_kind["overdue"].payload["actions"]] == [
            "to_today",
            "to_tomorrow",
        ]
        await ApplySuggestionUseCase(_svc(s)).execute(_USER, by_kind["overdue"].id, 1, now=_NOW)
        await DismissSuggestionUseCase(_svc(s)).execute(
            _USER, by_kind["free_slot"].id, "wrong_time"
        )
        await DismissSuggestionUseCase(_svc(s)).execute(_USER, by_kind["free_slot"].id)  # 한 번만
        events = await _events(s)
    assert sorted(events) == sorted(
        [
            ("sugg_shown", "todo_lr_late"),
            ("sugg_shown", "todo_lr_free"),
            ("todo_moved", "todo_lr_late"),  # 적용도 할 일 수정이라 남는다(출처 붙음 — 미룸 아님)
            ("sugg_applied", "todo_lr_late"),
            ("sugg_dismissed", "todo_lr_free"),
        ]
    )
    async with factory.begin() as s:
        repo = BehaviorRepository(s)
        cached = await repo.find_model(_USER)
        # 추천 때 계산 → 그 뒤 적용·넘김 기록으로 서명이 달라졌다(다시 계산해야 함)
        assert cached is not None and cached[2] != await repo.event_signature(_USER)
        model = await LearningService(repo, AiSettingsRepository(s)).model(_USER, _TODAY, _NOW)
        assert model.deferrals == {}  # 추천대로 옮긴 것은 미룸이 아니다
        assert model.reactions == 2
        cached = await repo.find_model(_USER)
        assert cached is not None and cached[2] == await repo.event_signature(_USER)


async def test_drop_goes_to_trash_and_undo_restores(factory):
    async with factory.begin() as s:
        repo = BehaviorRepository(s)
        for i in range(2):  # 두 번 미룬 기록 → 내려놓기
            await repo.add_event(
                _USER,
                BehaviorEvent(
                    type="todo_moved",
                    created_at=_NOW - timedelta(days=3 - i),
                    todo_id="todo_lr_late",
                    data={"from": f"2026-11-{11 + i}", "to": f"2026-11-{12 + i}"},
                ),
            )
    async with factory.begin() as s:
        got = await GetSuggestionsUseCase(_svc(s)).execute(_USER, _TODAY, now=_NOW)
        overdue = next(g for g in got if g.kind == "overdue")
        assert overdue.payload["reason_code"] == "overdue_deferred"
        assert overdue.payload["actions"][0]["code"] == "drop"
        # 오래된 화면: 0번이 '오늘로' 였다고 믿고 code 를 같이 보내면 거부된다
        with pytest.raises(AiSuggestionActionInvalidException):
            await ApplySuggestionUseCase(_svc(s)).execute(
                _USER, overdue.id, 0, now=_NOW, action_code="to_today"
            )
        applied = await ApplySuggestionUseCase(_svc(s)).execute(
            _USER, overdue.id, now=_NOW, action_code="drop"
        )
        assert applied.applied["dropped"] is True
        assert await TodoRepository(s).find_by_id("todo_lr_late", _USER) is None  # 휴지통
        await UndoSuggestionUseCase(_svc(s)).execute(_USER, overdue.id)
        assert (await TodoRepository(s).find_by_id("todo_lr_late", _USER)) is not None


async def test_undo_drop_after_manual_restore(factory):
    """내려놓은 할 일을 휴지통에서 직접 되살렸어도 추천은 되돌릴 수 있다."""
    async with factory.begin() as s:
        repo = BehaviorRepository(s)
        for i in range(2):
            await repo.add_event(
                _USER,
                BehaviorEvent(
                    type="todo_moved", created_at=_NOW - timedelta(days=3 - i),
                    todo_id="todo_lr_late",
                    data={"from": f"2026-11-{11 + i}", "to": f"2026-11-{12 + i}"},
                ),
            )
    async with factory.begin() as s:
        svc = _svc(s)
        got = await GetSuggestionsUseCase(svc).execute(_USER, _TODAY, now=_NOW)
        overdue = next(g for g in got if g.kind == "overdue")
        await ApplySuggestionUseCase(svc).execute(_USER, overdue.id, now=_NOW, action_code="drop")
        assert await svc.todos.restore(_USER, "todo_lr_late")  # 사용자가 휴지통에서 직접
        undone = await UndoSuggestionUseCase(svc).execute(_USER, overdue.id)
        assert undone.status == "shown"


async def test_rule_dropout_is_not_hidden_but_rank_hide_is(factory):
    """규칙에서 빠진 추천은 숨김이 아니고(보였던 동안 반응 없으면 무시), 순위에서 숨긴 것만 숨김."""
    async with factory.begin() as s:
        got = await GetSuggestionsUseCase(_svc(s)).execute(_USER, _TODAY, now=_NOW)
        assert {g.kind for g in got} >= {"overdue", "free_slot"}
        # 빈 칸 추천이 더는 후보가 아니게(시간을 직접 정함) — 학습 알림 없이 직접 고친다
        await s.execute(
            text(
                "UPDATE todos SET start_time = '2026-11-16 08:00+00',"
                " end_time = '2026-11-16 09:00+00', timezone = 'Asia/Seoul'"
                " WHERE id = 'todo_lr_free'"
            )
        )
        # 지난 마감 종류를 거의 늘 숨기는 통계(반응 충분) — 캐시를 지금 서명으로 저장
        repo = BehaviorRepository(s)
        low = BehaviorModel(accept={"overdue": Arm(0, 5000)}, reactions=100)
        await repo.save_model(_USER, low, _NOW, await repo.event_signature(_USER))
    for _ in range(2):  # 두 번 불러도 한 번만 남긴다
        async with factory.begin() as s:
            got = await GetSuggestionsUseCase(_svc(s)).execute(_USER, _TODAY, now=_NOW)
            assert got == []
    async with factory.begin() as s:
        events = await _events(s)
        assert events.count(("sugg_hidden", "todo_lr_late")) == 1
        assert ("sugg_hidden", "todo_lr_free") not in events
        # 다시 잘 받아들이는 통계 → 다시 보이고 sugg_shown 이 또 남는다
        repo = BehaviorRepository(s)
        high = BehaviorModel(accept={"overdue": Arm(5000, 0)}, reactions=100)
        await repo.save_model(_USER, high, _NOW, await repo.event_signature(_USER))
    async with factory.begin() as s:
        got = await GetSuggestionsUseCase(_svc(s)).execute(_USER, _TODAY, now=_NOW)
        [overdue] = got
        assert overdue.kind == "overdue" and "hidden" not in overdue.payload
    async with factory.begin() as s:  # text() 조회는 autoflush 하지 않아 커밋 뒤에 본다
        events = await _events(s)
    assert events.count(("sugg_shown", "todo_lr_late")) == 2


async def test_payload_update_does_not_overwrite_concurrent_apply(factory):
    from app.ai.infrastructure.persistence.repositories.suggestion_repo import (
        SuggestionRepository,
    )

    async with factory.begin() as s:
        got = await GetSuggestionsUseCase(_svc(s)).execute(_USER, _TODAY, now=_NOW)
        overdue = next(g for g in got if g.kind == "overdue")
    async with factory() as a:  # GET 이 행을 읽은 뒤
        await a.begin()
        [prev] = [x for x in await SuggestionRepository(a).list_for_date(_USER, "2026-11-16")
                  if x.id == overdue.id]
        async with factory.begin() as b:  # 다른 요청이 적용하고 커밋
            await ApplySuggestionUseCase(_svc(b)).execute(
                _USER, overdue.id, now=_NOW, action_code="to_today"
            )
        updated = await SuggestionRepository(a).update_payload_if_shown(
            prev.id, _USER, {**prev.payload, "hidden": True}
        )
        await a.commit()
    assert updated is None
    async with factory.begin() as s:
        row = await SuggestionRepository(s).find_by_id(overdue.id, _USER)
        assert row.status == "applied" and row.applied is not None


async def test_new_event_after_recompute_is_not_lost(factory):
    async with factory.begin() as s:
        learning = LearningService(BehaviorRepository(s), AiSettingsRepository(s))
        await learning.model(_USER, _TODAY, _NOW)
    async with factory.begin() as s:  # 계산 뒤 들어온 기록
        await BehaviorRepository(s).add_event(
            _USER,
            BehaviorEvent(type="todo_moved", created_at=_NOW, todo_id="todo_lr_late",
                          data={"from": "2026-11-10", "to": "2026-11-12"}),
        )
    async with factory.begin() as s:
        learning = LearningService(BehaviorRepository(s), AiSettingsRepository(s))
        model = await learning.model(_USER, _TODAY, _NOW)  # 6시간 안이어도 다시 계산
        assert model.deferrals == {"todo_lr_late": 1}


async def test_dismiss_closes_dropped_suggestion(factory):
    """내려놓은 할 일이 영구 삭제돼 되돌릴 수 없으면 넘기기로 닫는다(넘김으로 기록하지 않음)."""
    async with factory.begin() as s:
        repo = BehaviorRepository(s)
        for i in range(2):
            await repo.add_event(
                _USER,
                BehaviorEvent(
                    type="todo_moved", created_at=_NOW - timedelta(days=3 - i),
                    todo_id="todo_lr_late",
                    data={"from": f"2026-11-{11 + i}", "to": f"2026-11-{12 + i}"},
                ),
            )
    async with factory.begin() as s:
        svc = _svc(s)
        got = await GetSuggestionsUseCase(svc).execute(_USER, _TODAY, now=_NOW)
        overdue = next(g for g in got if g.kind == "overdue")
        await ApplySuggestionUseCase(svc).execute(_USER, overdue.id, now=_NOW, action_code="drop")
        await s.execute(text("DELETE FROM todos WHERE id = 'todo_lr_late'"))  # 영구 삭제
        with pytest.raises(AiSuggestionNotFoundException):
            await UndoSuggestionUseCase(svc).execute(_USER, overdue.id)
    async with factory.begin() as s:
        closed = await DismissSuggestionUseCase(_svc(s)).execute(_USER, overdue.id)
        assert closed.status == "dismissed"
        assert ("sugg_dismissed", "todo_lr_late") not in await _events(s)


async def test_learning_off_records_nothing_and_reset_clears(factory):
    async with factory.begin() as s:
        await GetSuggestionsUseCase(_svc(s)).execute(_USER, _TODAY, now=_NOW)
        assert await _events(s)
        await AiSettingsUseCase(AiSettingsRepository(s)).patch(_USER, {"learning_enabled": False})
    async with factory.begin() as s:
        svc = _svc(s)
        assert await svc.learning.model(_USER, _TODAY, _NOW) is None
        await svc.learning.reset(_USER)
        got = await GetSuggestionsUseCase(svc).execute(_USER, _TODAY + timedelta(days=1),
                                                       now=_NOW + timedelta(days=1))
        assert got  # 추천은 그대로 나온다
        assert await _events(s) == []
        assert all(not g.payload["learned"] for g in got)


async def test_usage_learning_metrics(factory):
    from app.ai.application.use_cases.usage import AiUsageService, GetAiUsageUseCase
    from app.ai.infrastructure.persistence.repositories.suggestion_repo import AiUsageRepository
    from app.user.infrastructure.persistence.repositories.user_repo import UserRepository

    async with factory.begin() as s:
        got = await GetSuggestionsUseCase(_svc(s)).execute(_USER, _TODAY, now=_NOW)
        overdue = next(g for g in got if g.kind == "overdue")
        await ApplySuggestionUseCase(_svc(s)).execute(_USER, overdue.id, 0, now=_NOW)
        await UndoSuggestionUseCase(_svc(s)).execute(_USER, overdue.id)
        # 되돌리면 적용이 남긴 '옮김' 도 지운다 — 되돌린 변경은 세지 않는다
        assert [t for t, _ in await _events(s)].count("todo_moved") == 0
    async with factory.begin() as s:
        learning = LearningService(BehaviorRepository(s), AiSettingsRepository(s))
        usage = AiUsageService(AiUsageRepository(s), UserRepository(s), 50, 1000)
        report = await GetAiUsageUseCase(usage, learning).execute(
            _USER, now=datetime.now(UTC)
        )
    m = report.learning
    assert m is not None and m.enabled and not m.ready
    assert (m.shown, m.applied, m.undone, m.dismissed) == (2, 1, 1, 0)
