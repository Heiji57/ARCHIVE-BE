"""소스(회고·할일·하위 요약)가 없는 기간은 AI 를 호출하지 않는다.

자동 요약은 활동 없는 사용자에게도 매 주기 돌기 때문에, 빈 기간마다 Gemini 를 부르던
비용이 "사용자 수 × 주기" 로 쌓였다. 빈 기간 요약은 안내 문구로 완료하고(`is_empty`),
상위 요약은 그 안내 문구를 입력으로 쓰지 않는다.
"""
import json
from datetime import UTC, date, datetime
from types import SimpleNamespace

import app.retrospective.infrastructure.ai.strategies as strategies_module
import app.worker.tasks.generate_summary as generate_summary_module
from app.retrospective.domain.constants.summary_empty_defaults import empty_summary_text
from app.retrospective.domain.models.retro_summary import RetroSummary
from app.retrospective.domain.models.value_objects import (
    SummaryContent,
    SummaryStatus,
    SummaryType,
)
from app.todo.domain.models.value_objects import TaskStatus

_NOW = datetime.now(UTC)
_EMPTY_TEXT = empty_summary_text("ko")


def _summary(
    summary_type: SummaryType,
    start: date,
    end: date,
    *,
    status: SummaryStatus = SummaryStatus.PENDING,
    content: str | None = None,
    is_empty: bool = False,
) -> RetroSummary:
    return RetroSummary(
        id=f"summ_{summary_type.value}_{start}",
        user_id="usr_1",
        summary_type=summary_type,
        period_start=start,
        period_end=end,
        status=status,
        content=SummaryContent.from_text(content) if content else None,
        is_empty=is_empty,
        created_at=_NOW,
    )


def _entry(date_key: str, content: str) -> SimpleNamespace:
    return SimpleNamespace(
        date_key=date_key,
        retro_type=SimpleNamespace(value="daily"),
        title=f"{date_key} 회고",
        content=content,
        created_at=_NOW,
    )


def _patch_repos(monkeypatch, *, entries=(), todos=(), summaries=None, completed_weeklies=()):
    summaries = summaries or {}

    class _EntryRepo:
        def __init__(self, session) -> None:
            pass

        async def find_by_period(self, user_id, start, end):
            return [e for e in entries if start.isoformat() <= e.date_key <= end.isoformat()]

    class _TodoRepo:
        def __init__(self, session) -> None:
            pass

        async def find_by_date_range(self, user_id, start, end):
            return list(todos)

    class _SummaryRepo:
        def __init__(self, session) -> None:
            pass

        async def find_by_period(self, user_id, summary_type, start):
            return summaries.get((summary_type, start))

        async def find_completed_in_range(self, user_id, summary_type, start, end):
            return list(completed_weeklies)

    async def calendar(session, summary):
        return [
            SimpleNamespace(date_key="2026-08-25", title="팀 회의", time_range=None, location=None)
        ]

    monkeypatch.setattr(strategies_module, "JournalEntryRepository", _EntryRepo)
    monkeypatch.setattr(strategies_module, "TodoRepository", _TodoRepo)
    monkeypatch.setattr(strategies_module, "RetroSummaryRepository", _SummaryRepo)
    monkeypatch.setattr(strategies_module, "_fetch_calendar_inputs", calendar)


# ── 전략 ─────────────────────────────────────────────────────────


async def test_weekly_with_only_calendar_events_is_empty(monkeypatch) -> None:
    not_started = SimpleNamespace(status=TaskStatus.NOT_START)
    _patch_repos(monkeypatch, todos=[not_started])
    week = _summary(SummaryType.WEEKLY, date(2026, 8, 24), date(2026, 8, 30))
    prompt = await strategies_module.EntriesAndTodosStrategy().build_prompt(None, week, "", "ko")
    assert prompt is None, "일정·시작 안 한 할일만으로는 요약하지 않는다"


async def test_weekly_with_an_entry_builds_prompt(monkeypatch) -> None:
    _patch_repos(monkeypatch, entries=[_entry("2026-08-25", "배포 자동화 회고")])
    week = _summary(SummaryType.WEEKLY, date(2026, 8, 24), date(2026, 8, 30))
    prompt = await strategies_module.EntriesAndTodosStrategy().build_prompt(None, week, "", "ko")
    assert prompt is not None and "배포 자동화 회고" in prompt


async def test_monthly_ignores_empty_weekly_summaries(monkeypatch) -> None:
    month = _summary(SummaryType.MONTHLY, date(2026, 8, 1), date(2026, 8, 31))
    weeks = strategies_module.weeks_owned_by_month(2026, 8)
    empty_weeklies = {
        (SummaryType.WEEKLY, w_start): _summary(
            SummaryType.WEEKLY, w_start, w_end,
            status=SummaryStatus.COMPLETED, content=_EMPTY_TEXT, is_empty=True,
        )
        for w_start, w_end in weeks
    }
    _patch_repos(monkeypatch, summaries=empty_weeklies)
    prompt = await strategies_module.MonthlyHybridStrategy().build_prompt(None, month, "", "ko")
    assert prompt is None


async def test_monthly_uses_backdated_entry_behind_empty_weekly(monkeypatch) -> None:
    """빈 주간 요약 뒤에 과거 날짜로 쓴 회고는 원문으로 들어가야 한다 — 안내 문구가 아니라."""
    month = _summary(SummaryType.MONTHLY, date(2026, 8, 1), date(2026, 8, 31))
    w_start, w_end = strategies_module.weeks_owned_by_month(2026, 8)[0]
    empty_weekly = _summary(
        SummaryType.WEEKLY, w_start, w_end,
        status=SummaryStatus.COMPLETED, content=_EMPTY_TEXT, is_empty=True,
    )
    _patch_repos(
        monkeypatch,
        entries=[_entry(w_start.isoformat(), "뒤늦게 쓴 회고")],
        summaries={(SummaryType.WEEKLY, w_start): empty_weekly},
    )
    prompt = await strategies_module.MonthlyHybridStrategy().build_prompt(None, month, "", "ko")
    assert prompt is not None
    assert "뒤늦게 쓴 회고" in prompt
    assert _EMPTY_TEXT not in prompt


async def test_annual_with_only_empty_children_is_empty(monkeypatch) -> None:
    year = _summary(SummaryType.ANNUAL, date(2026, 1, 1), date(2026, 12, 31))
    empty_monthly = {
        (SummaryType.MONTHLY, m_start): _summary(
            SummaryType.MONTHLY, m_start, m_end,
            status=SummaryStatus.COMPLETED, content=_EMPTY_TEXT, is_empty=True,
        )
        for m_start, m_end in strategies_module.get_months_in_year(2026)
    }
    _patch_repos(
        monkeypatch,
        summaries=empty_monthly,
        completed_weeklies=[
            _summary(
                SummaryType.WEEKLY, date(2026, 3, 2), date(2026, 3, 8),
                status=SummaryStatus.COMPLETED, content=_EMPTY_TEXT, is_empty=True,
            )
        ],
    )
    assert await strategies_module.AnnualHybridStrategy().build_prompt(None, year, "", "ko") is None


# ── 도메인 ───────────────────────────────────────────────────────


def test_regenerated_summary_clears_empty_flag() -> None:
    s = _summary(SummaryType.WEEKLY, date(2026, 8, 24), date(2026, 8, 30))
    s.complete(SummaryContent.from_text(_EMPTY_TEXT), is_empty=True)
    assert s.is_empty and s.status == SummaryStatus.COMPLETED
    s.complete(SummaryContent.from_text("실제 요약"))
    assert not s.is_empty


# ── 워커 ─────────────────────────────────────────────────────────


class _Ctx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> bool:
        return False


class _Factory:
    def begin(self) -> _Ctx:
        return _Ctx()


async def test_worker_skips_gemini_and_notification_for_empty_period(monkeypatch) -> None:
    summary = _summary(SummaryType.WEEKLY, date(2026, 8, 24), date(2026, 8, 30))
    published: list[tuple[str, str]] = []
    saved_notifications: list[object] = []

    class _SummaryRepo:
        def __init__(self, session) -> None:
            pass

        async def find_by_id(self, summary_id, user_id):
            return summary

        async def save(self, s):
            return s

    class _SettingsRepo:
        def __init__(self, session) -> None:
            pass

        async def find_by_user_id(self, user_id):
            return None

    class _EmptyStrategy:
        async def build_prompt(self, session, s, template, locale):
            return None

    class _NeverGemini:
        def __init__(self, ai) -> None:
            raise AssertionError("빈 기간에 Gemini 를 호출하면 안 된다")

    class _NotificationRepo:
        def __init__(self, session) -> None:
            pass

        async def save(self, n):
            saved_notifications.append(n)
            return n

    class _Redis:
        async def publish(self, channel, message):
            published.append((channel, message))

        async def aclose(self):
            pass

    monkeypatch.setattr(generate_summary_module, "get_worker_session_factory", lambda: _Factory())
    monkeypatch.setattr(generate_summary_module, "RetroSummaryRepository", _SummaryRepo)
    monkeypatch.setattr(generate_summary_module, "UserSettingsRepository", _SettingsRepo)
    monkeypatch.setattr(generate_summary_module, "get_strategy", lambda t: _EmptyStrategy())
    monkeypatch.setattr(generate_summary_module, "GeminiSummaryClient", _NeverGemini)
    monkeypatch.setattr(generate_summary_module, "NotificationRepository", _NotificationRepo)
    monkeypatch.setattr(generate_summary_module.Redis, "from_url", lambda *a, **kw: _Redis())

    await generate_summary_module.generate_summary_task.run(
        summary.id, "usr_1", send_notification=True
    )

    assert summary.status == SummaryStatus.COMPLETED
    assert summary.is_empty
    assert summary.content is not None and summary.content.text == _EMPTY_TEXT
    assert saved_notifications == [], "빈 기간 요약에는 알림을 보내지 않는다"
    assert (f"summary:{summary.id}", json.dumps(
        {"status": "completed", "summary_id": summary.id}
    )) in published, "SSE 구독자에게는 완료를 알려야 한다"
    assert not any(ch.startswith("notifications:") for ch, _ in published)
