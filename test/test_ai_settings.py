"""AI 설정·기억·예약(5c) — 설정 병합, 대화에 넘길 값, 상한, 예약 실행 시각, 대화 기록 정리."""

import os
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.shared.infrastructure.database.models  # noqa: F401  (FK 대상 테이블 등록)
from app.ai.application.use_cases.ai_settings import AiSettingsUseCase
from app.ai.domain.exceptions.exceptions import AiMemoryLimitExceededException
from app.ai.domain.models.ai_settings import AiSchedule
from app.ai.domain.services.schedule_rules import schedule_due
from app.ai.infrastructure.persistence.repositories.ai_settings_repo import (
    AiRetentionRepository,
    AiSettingsRepository,
)
from app.ai.presentation.requests.requests import (
    CreateScheduleRequest,
    PatchAiSettingsRequest,
)

_SEOUL = ZoneInfo("Asia/Seoul")


def _sched(**kw) -> AiSchedule:
    base = dict(
        id="s1",
        user_id="u",
        prompt="내일 일정 정리해줘",
        repeat={"unit": "week", "weekdays": [1, 3], "at": "08:30"},
        created_at=datetime(2026, 11, 1, tzinfo=UTC),
    )
    base.update(kw)
    return AiSchedule(**base)


def test_schedule_due_window_weekday_and_once_per_day():
    mon_0835 = datetime(2026, 11, 16, 8, 35, tzinfo=_SEOUL)  # 월(1)
    assert schedule_due(_sched(), mon_0835)
    assert not schedule_due(_sched(), mon_0835.replace(hour=8, minute=20))  # 아직
    assert not schedule_due(_sched(), mon_0835.replace(hour=9, minute=40))  # 1시간 지남
    assert not schedule_due(_sched(), mon_0835 + timedelta(days=1))  # 화(2)
    assert not schedule_due(_sched(last_run_date=date(2026, 11, 16)), mon_0835)
    assert not schedule_due(_sched(enabled=False), mon_0835)
    daily = _sched(repeat={"unit": "day", "at": "08:30"})
    assert schedule_due(daily, mon_0835 + timedelta(days=1))


@pytest.mark.parametrize(
    "repeat",
    [
        {"unit": "week", "at": "08:30"},
        {"unit": "week", "weekdays": [7], "at": "08:30"},
        {"unit": "day", "at": "25:00"},
        {"unit": "month", "at": "08:30"},
    ],
)
def test_schedule_repeat_validation(repeat):
    with pytest.raises(ValidationError):
        CreateScheduleRequest.model_validate({"prompt": "x", "repeat": repeat})


def test_settings_patch_rejects_unknown_tool_and_retention():
    with pytest.raises(ValidationError):
        PatchAiSettingsRequest.model_validate({"tools": {"email": False}})
    with pytest.raises(ValidationError):
        PatchAiSettingsRequest.model_validate({"retentionDays": 7})


# ── DB ───────────────────────────────────────────────────────────────────────

_TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://ADMIN:heijiADMIN20090220!@localhost:5437/archive",
)
_USER = "usr_redesign_aiset"


@pytest.fixture
async def factory():
    engine = create_async_engine(_TEST_DB_URL)
    f = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with f.begin() as s:
            if await s.scalar(text("SELECT to_regclass('public.ai_settings')")) is None:
                pytest.skip("TEST_DATABASE_URL 의 DB 가 최신 마이그레이션이 아니다")
    except OSError:
        pytest.skip("test DB unavailable")
    async with f.begin() as s:
        await s.execute(text("DELETE FROM users WHERE id = :id"), {"id": _USER})
        await s.execute(
            text(
                "INSERT INTO users (id, email, created_at, country, timezone)"
                " VALUES (:id, 'aiset@example.invalid', now(), 'KR', 'Asia/Seoul')"
            ),
            {"id": _USER},
        )
    yield f
    async with f.begin() as s:
        await s.execute(text("DELETE FROM users WHERE id = :id"), {"id": _USER})
    await engine.dispose()


async def test_settings_merge_and_turn_options(factory):
    async with factory.begin() as s:
        uc = AiSettingsUseCase(AiSettingsRepository(s))
        assert (await uc.get(_USER)).retention_days == 90  # 행이 없어도 기본값
        await uc.patch(_USER, {"tools": {"github": False}, "answer_length": "short"})
        await uc.patch(_USER, {"tools": {"retro": False}})
        got = await uc.get(_USER)
        assert got.tools == {"calendar": True, "todo": True, "retro": False, "github": False}
        await uc.add_memory(_USER, "아침엔 회의를 넣지 마")
        opts = await uc.turn_options(_USER)
        assert opts["enabled_sources"] == frozenset({"calendar", "todo"})
        assert opts["memories"] == ["아침엔 회의를 넣지 마"] and opts["answer_length"] == "short"
        await uc.patch(_USER, {"memory_enabled": False})
        assert (await uc.turn_options(_USER))["memories"] == []


async def test_memory_limit(factory):
    async with factory.begin() as s:
        uc = AiSettingsUseCase(AiSettingsRepository(s))
        for i in range(50):
            await uc.add_memory(_USER, f"기억 {i}")
        with pytest.raises(AiMemoryLimitExceededException):
            await uc.add_memory(_USER, "하나 더")


async def test_retention_purges_old_conversations_and_unapplied_proposals(factory):
    old = datetime.now(UTC) - timedelta(days=100)
    async with factory.begin() as s:
        await s.execute(
            text(
                "INSERT INTO ai_conversations (id, user_id, title, created_at, updated_at) VALUES"
                " ('conv_old', :u, 'old', :old, :old), ('conv_new', :u, 'new', now(), now())"
            ),
            {"u": _USER, "old": old},
        )
        await s.execute(
            text(
                "INSERT INTO ai_proposals (id, user_id, conversation_id, kind, payload, status,"
                " created_at) VALUES"
                " ('p_pending', :u, 'conv_old', 'add', '{}', 'pending', :old),"
                " ('p_applied', :u, 'conv_old', 'add', '{}', 'applied', :old)"
            ),
            {"u": _USER, "old": old},
        )
        removed = await AiRetentionRepository(s).purge_older_than(
            _USER, datetime.now(UTC) - timedelta(days=90)
        )
        assert removed == 1
        convs = set(
            (
                await s.execute(
                    text("SELECT id FROM ai_conversations WHERE user_id=:u"), {"u": _USER}
                )
            ).scalars()
        )
        props = set(
            (
                await s.execute(text("SELECT id FROM ai_proposals WHERE user_id=:u"), {"u": _USER})
            ).scalars()
        )
        assert convs == {"conv_new"} and props == {"p_applied"}


async def test_schedule_claim_run_is_once_per_day(factory):
    async with factory.begin() as s:
        uc = AiSettingsUseCase(AiSettingsRepository(s))
        sched = await uc.create_schedule(_USER, "아침 정리", {"unit": "day", "at": "08:00"}, True)
        repo = AiSettingsRepository(s)
        assert await repo.claim_run(sched.id, date(2026, 11, 16)) is True
        assert await repo.claim_run(sched.id, date(2026, 11, 16)) is False
        assert await repo.claim_run(sched.id, date(2026, 11, 17)) is True
