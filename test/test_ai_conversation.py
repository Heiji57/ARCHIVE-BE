"""AI 대화와 제안(5b) — 가짜 모델로 실제 도구 루프를 돌리고, 제안 적용·되돌리기를 실제 DB 에서.

- 읽기 도구는 바로, 쓰기는 제안으로만 — 차례가 끝나도 할 일은 그대로다.
- 진행은 step / proposal / delta 이벤트로 흐르고, 답 메시지가 저장되고, 사용량이 쌓인다.
- 적용 전에 대상이 바뀌었으면 AI_PROPOSAL_STALE. 되돌리기는 적용 뒤 사용자가 고친 항목을 건너뛴다.
- 설정에서 끈 출처의 도구는 모델에게 넘기지 않고, 불러도 오류 결과만 돌려준다.
"""

import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.shared.infrastructure.database.models  # noqa: F401  (FK 대상 테이블 등록)
from app.ai.application.services.agent import AgentContext, run_turn
from app.ai.application.use_cases.conversations import (
    ConversationsUseCase,
    MessageNotYetVisibleError,
    PostMessageUseCase,
    RunAiTurnUseCase,
)
from app.ai.application.use_cases.proposals import ProposalsUseCase
from app.ai.application.use_cases.usage import AiUsageService
from app.ai.domain.exceptions.exceptions import (
    AiProposalAlreadyAppliedException,
    AiProposalStaleException,
)
from app.ai.domain.models.agent import ModelTurn, ToolCall
from app.ai.infrastructure.adapters.retro_adapter import RetroAdapter
from app.ai.infrastructure.adapters.todo_adapter import TodoAdapter
from app.ai.infrastructure.persistence.repositories.conversation_repo import (
    ConversationRepository,
    ProposalRepository,
)
from app.ai.infrastructure.persistence.repositories.suggestion_repo import AiUsageRepository
from app.calendars.infrastructure.persistence.repositories.calendar_repo import CalendarRepository
from app.retrospective.application.use_cases.create_entry import CreateEntryUseCase
from app.retrospective.application.use_cases.delete_entry import DeleteEntryUseCase
from app.retrospective.infrastructure.persistence.repositories.journal_entry_repo import (
    JournalEntryRepository,
)
from app.settings.domain.models.user_settings import UserSettings
from app.settings.infrastructure.persistence.repositories.user_settings_repo import (
    UserSettingsRepository,
)
from app.todo.application.use_cases.batch_update_todos import BatchUpdateTodosUseCase
from app.todo.application.use_cases.create_todo import CreateTodoUseCase
from app.todo.application.use_cases.delete_todo import DeleteTodoUseCase
from app.todo.application.use_cases.update_todo import UpdateTodoUseCase
from app.todo.infrastructure.persistence.repositories.todo_repo import TodoRepository
from app.topic.infrastructure.persistence.repositories.chunk_repo import TodoEmbeddingRepository
from app.user.infrastructure.persistence.repositories.user_repo import UserRepository

_TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://ADMIN:heijiADMIN20090220!@localhost:5437/archive",
)
_USER = "usr_redesign_chat"


class _Queue:
    async def enqueue(self, *a):
        pass


class _NoCommits:
    async def messages_on(self, user_id, day):
        return []

    async def list_range(self, user_id, a, b):
        return []


class _Sink:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def emit(self, event):
        self.events.append(event)


class _ScriptedModel:
    """차례마다 정해 둔 응답을 돌려주고, 받은 도구 목록·기록을 남긴다."""

    def __init__(self, turns: list[ModelTurn]) -> None:
        self._turns = turns
        self.seen_tools: list[list[str]] = []
        self.seen_history: list[list] = []

    async def generate(self, system, history, tools):
        self.seen_tools.append([t.name for t in tools])
        self.seen_history.append(list(history))
        return self._turns.pop(0)


@pytest.fixture
async def factory():
    engine = create_async_engine(_TEST_DB_URL)
    f = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with f.begin() as s:
            if await s.scalar(text("SELECT to_regclass('public.ai_proposals')")) is None:
                pytest.skip("TEST_DATABASE_URL 의 DB 가 최신 마이그레이션이 아니다")
    except OSError:
        pytest.skip("test DB unavailable")
    async with f.begin() as s:
        await s.execute(text("DELETE FROM users WHERE id = :id"), {"id": _USER})
        await s.execute(
            text(
                "INSERT INTO users (id, email, created_at, country, timezone)"
                " VALUES (:id, 'chat@example.invalid', now(), 'KR', 'Asia/Seoul')"
            ),
            {"id": _USER},
        )
        await s.execute(
            text(
                "INSERT INTO todos (id, user_id, title, status, date_key, created_at, tags)"
                " VALUES ('todo_chat_1', :u, '기획서 정리', 'not-start', '2026-11-16', now(), '{}')"
            ),
            {"u": _USER},
        )
    yield f
    async with f.begin() as s:
        await s.execute(text("DELETE FROM users WHERE id = :id"), {"id": _USER})
    await engine.dispose()


def _todo_port(s) -> TodoAdapter:
    repo, cal = TodoRepository(s), CalendarRepository(s)
    return TodoAdapter(
        repo,
        BatchUpdateTodosUseCase(repo, UpdateTodoUseCase(repo, cal)),
        _Queue(),  # type: ignore[arg-type]
        CreateTodoUseCase(repo, UserSettingsRepository(s), cal),
        DeleteTodoUseCase(repo),
        TodoEmbeddingRepository(s),
        None,  # type: ignore[arg-type]  # 휴지통 되살리기 — 이 테스트에선 안 씀
        None,  # type: ignore[arg-type]  # 행동 학습 알림 — 이 테스트에선 안 씀
    )


def _retro_port(s) -> RetroAdapter:
    entries = JournalEntryRepository(s)
    return RetroAdapter(
        entries,
        CreateEntryUseCase(entries, UserSettingsRepository(s)),
        DeleteEntryUseCase(entries),
        _Queue(),  # type: ignore[arg-type]
    )


def _usage(s) -> AiUsageService:
    return AiUsageService(AiUsageRepository(s), UserRepository(s), 50, 1000)


def _proposals(s) -> ProposalsUseCase:
    return ProposalsUseCase(ProposalRepository(s), _todo_port(s), _retro_port(s))


_MOVE = ToolCall(
    "propose_moves",
    {
        "summary": "기획서를 내일 오후로 옮길게요",
        "items": [
            {"todo_id": "todo_chat_1", "date": "2026-11-17", "start": "14:00", "end": "15:00"}
        ],
    },
)


async def _turn_with_move(s, model) -> tuple:
    conv = await ConversationsUseCase(ConversationRepository(s)).create(_USER)
    msg = await PostMessageUseCase(ConversationRepository(s), _usage(s)).execute(
        _USER, conv.id, "기획서 내일로 옮겨줘", None
    )
    sink = _Sink()
    uc = RunAiTurnUseCase(
        ConversationRepository(s),
        ProposalRepository(s),
        _todo_port(s),
        _NoCommits(),
        _retro_port(s),
        model,
        _usage(s),
        UserSettingsRepository(s),
        UserRepository(s),
    )
    outcome, answer_id = await uc.execute(_USER, conv.id, sink, expect_message_id=msg.id)
    return conv, outcome, answer_id, sink


async def test_turn_reads_then_proposes_without_changing_data(factory):
    model = _ScriptedModel(
        [
            ModelTurn(
                text=None,
                calls=(ToolCall("list_todos", {"from": "2026-11-16", "to": "2026-11-17"}),),
            ),
            ModelTurn(text=None, calls=(_MOVE,)),
            ModelTurn(
                text="내일 오후 2시로 옮기는 제안을 만들었어요.", input_tokens=10, output_tokens=5
            ),
        ]
    )
    async with factory.begin() as s:
        conv, outcome, answer_id, sink = await _turn_with_move(s, model)
        types = [e["type"] for e in sink.events]
        assert types[0] == "step" and "proposal" in types and types[-1] == "delta"
        proposal = next(e for e in sink.events if e["type"] == "proposal")["proposal"]
        assert proposal["kind"] == "move" and proposal["status"] == "pending"
        item = proposal["items"][0]
        assert item["before"]["date_key"] == "2026-11-16"
        assert item["after"]["start_time"] == "2026-11-17T05:00:00+00:00"  # KST 14:00
        # 모델은 첫 차례에 도구 결과로 실제 할 일을 봤다
        tool_msg = model.seen_history[1][-1]
        assert tool_msg.results[0].payload["todos"][0]["id"] == "todo_chat_1"
        # 데이터는 그대로 — 제안일 뿐
        assert (await TodoRepository(s).find_by_id("todo_chat_1", _USER)).date_key == "2026-11-16"
        msgs = await ConversationsUseCase(ConversationRepository(s)).messages(_USER, conv.id)
        assert [m.role for m in msgs] == ["user", "assistant"] and msgs[-1].id == answer_id
        assert (await _usage(s).report(_USER)).day_used == 1


async def test_apply_and_undo_move(factory):
    model = _ScriptedModel([ModelTurn(text=None, calls=(_MOVE,)), ModelTurn(text="ok")])
    async with factory.begin() as s:
        _, outcome, _, _ = await _turn_with_move(s, model)
        pid = outcome.proposal_ids[0]
        applied = await _proposals(s).apply(_USER, pid, None)
        moved = await TodoRepository(s).find_by_id("todo_chat_1", _USER)
        assert moved.date_key == "2026-11-17" and moved.start_time is not None
        with pytest.raises(AiProposalAlreadyAppliedException):
            await _proposals(s).apply(_USER, pid, None)
        result = await _proposals(s).undo(_USER, pid)
        assert result.skipped == [] and result.proposal.status == "undone"
        back = await TodoRepository(s).find_by_id("todo_chat_1", _USER)
        assert back.date_key == "2026-11-16" and back.start_time is None
        assert applied.applied["i1"]["previous"]["date_key"] == "2026-11-16"


async def test_stale_proposal_is_rejected(factory):
    model = _ScriptedModel([ModelTurn(text=None, calls=(_MOVE,)), ModelTurn(text="ok")])
    async with factory.begin() as s:
        _, outcome, _, _ = await _turn_with_move(s, model)
        await s.execute(text("UPDATE todos SET date_key='2026-11-20' WHERE id='todo_chat_1'"))
        with pytest.raises(AiProposalStaleException) as ei:
            await _proposals(s).apply(_USER, outcome.proposal_ids[0], None)
        assert ei.value.details == [{"key": "i1", "todoId": "todo_chat_1"}]


async def test_undo_skips_items_the_user_changed_after_apply(factory):
    add = ToolCall(
        "propose_todos",
        {
            "summary": "두 개 넣을게요",
            "items": [
                {"title": "회의", "date": "2026-11-18", "start": "10:00"},
                {"title": "정리", "date": "2026-11-18"},
            ],
        },
    )
    model = _ScriptedModel([ModelTurn(text=None, calls=(add,)), ModelTurn(text="ok")])
    async with factory.begin() as s:
        _, outcome, _, _ = await _turn_with_move(s, model)
        pid = outcome.proposal_ids[0]
        applied = await _proposals(s).apply(_USER, pid, ["i1", "i2"])
        meeting = applied.applied["i1"]["todo_id"]
        tidy = applied.applied["i2"]["todo_id"]
        # 기본 길이(60분)로 끝 시각이 채워졌다
        created = await TodoRepository(s).find_by_id(meeting, _USER)
        assert (created.end_time - created.start_time).seconds == 3600
        await s.execute(text("UPDATE todos SET date_key='2026-11-19' WHERE id=:id"), {"id": tidy})
        result = await _proposals(s).undo(_USER, pid)
        assert result.skipped == ["i2"]
        assert await TodoRepository(s).find_by_id(meeting, _USER) is None
        assert await TodoRepository(s).find_by_id(tidy, _USER) is not None


async def test_retro_draft_apply_and_undo(factory):
    draft = ToolCall(
        "propose_retro_draft",
        {"summary": "초안이에요", "date": "2026-11-16", "text": "오늘은 기획서를 정리했다."},
    )
    model = _ScriptedModel([ModelTurn(text=None, calls=(draft,)), ModelTurn(text="ok")])
    async with factory.begin() as s:
        _, outcome, _, _ = await _turn_with_move(s, model)
        applied = await _proposals(s).apply(_USER, outcome.proposal_ids[0], None)
        entry_id = applied.applied["i1"]["entry_id"]
        assert (await JournalEntryRepository(s).find_by_id(entry_id, _USER)).content.startswith(
            "오늘"
        )
        await _proposals(s).undo(_USER, outcome.proposal_ids[0])
        assert await JournalEntryRepository(s).find_by_id(entry_id, _USER) is None


async def test_turn_waits_until_user_message_is_visible(factory):
    async with factory.begin() as s:
        conv = await ConversationsUseCase(ConversationRepository(s)).create(_USER)
        uc = RunAiTurnUseCase(
            ConversationRepository(s),
            ProposalRepository(s),
            _todo_port(s),
            _NoCommits(),
            _retro_port(s),
            _ScriptedModel([]),
            _usage(s),
            UserSettingsRepository(s),
            UserRepository(s),
        )
        with pytest.raises(MessageNotYetVisibleError):
            await uc.execute(_USER, conv.id, _Sink(), expect_message_id="msg_not_committed")


async def test_disabled_source_tools_are_hidden_and_refused():
    from zoneinfo import ZoneInfo

    class _Never:
        async def list_range(self, *a):
            raise AssertionError("must not be called")

    model = _ScriptedModel(
        [
            ModelTurn(
                text=None,
                calls=(ToolCall("list_todos", {"from": "2026-11-16", "to": "2026-11-16"}),),
            ),
            ModelTurn(text="못 봐요"),
        ]
    )
    ctx = AgentContext(
        user_id=_USER,
        conversation_id=None,
        settings=UserSettings(user_id=_USER),
        tz=ZoneInfo("Asia/Seoul"),
        now=datetime(2026, 11, 16, 1, tzinfo=UTC),
        todos=_Never(),  # type: ignore[arg-type]
        commits=_NoCommits(),  # type: ignore[arg-type]
        retros=_Never(),  # type: ignore[arg-type]
        proposals=None,  # type: ignore[arg-type]
        sink=_Sink(),  # type: ignore[arg-type]
        enabled_sources=frozenset({"calendar", "github"}),
    )
    outcome = await run_turn(ctx, [], model)
    assert "list_todos" not in model.seen_tools[0] and "propose_todos" not in model.seen_tools[0]
    refused = model.seen_history[1][-1].results[0].payload
    assert "AI_TOOL_DISABLED" in refused["error"]
    assert outcome.text == "못 봐요"


# ── 리뷰 반영 ───────────────────────────────────────────────────────────────


def _bare_ctx(**kw):
    from zoneinfo import ZoneInfo

    base = dict(
        user_id=_USER,
        conversation_id=None,
        settings=UserSettings(user_id=_USER),
        tz=ZoneInfo("Asia/Seoul"),
        now=datetime(2026, 11, 16, 1, tzinfo=UTC),
        todos=None,
        commits=_NoCommits(),
        retros=None,
        proposals=None,
        sink=_Sink(),
    )
    base.update(kw)
    return AgentContext(**base)  # type: ignore[arg-type]


async def test_malformed_tool_args_return_error_not_crash():
    bad = ToolCall("propose_todos", {"summary": "x", "items": "회의 넣어줘"})
    model = _ScriptedModel([ModelTurn(text=None, calls=(bad,)), ModelTurn(text="다시 할게요")])
    outcome = await run_turn(_bare_ctx(), [], model)
    assert "error" in model.seen_history[1][-1].results[0].payload
    assert outcome.text == "다시 할게요"


async def test_last_step_is_forced_to_answer_in_text():
    from app.ai.application.services.agent import MAX_STEPS

    loop = ModelTurn(text=None, calls=(ToolCall("get_settings", {}),))
    model = _ScriptedModel([loop] * (MAX_STEPS - 1) + [ModelTurn(text="정리했어요")])
    outcome = await run_turn(_bare_ctx(), [], model)
    assert model.seen_tools[-1] == [] and outcome.text == "정리했어요"


async def test_retro_undo_keeps_user_edits(factory):
    draft = ToolCall(
        "propose_retro_draft", {"summary": "s", "date": "2026-11-16", "text": "초안 본문"}
    )
    model = _ScriptedModel([ModelTurn(text=None, calls=(draft,)), ModelTurn(text="ok")])
    async with factory.begin() as s:
        _, outcome, _, _ = await _turn_with_move(s, model)
        applied = await _proposals(s).apply(_USER, outcome.proposal_ids[0], None)
        entry_id = applied.applied["i1"]["entry_id"]
        await s.execute(
            text("UPDATE journal_entries SET content='내가 고친 글' WHERE id=:id"), {"id": entry_id}
        )
        result = await _proposals(s).undo(_USER, outcome.proposal_ids[0])
        assert result.skipped == ["i1"]
        assert (await JournalEntryRepository(s).find_by_id(entry_id, _USER)) is not None


async def test_virtual_slot_already_edited_makes_move_stale(factory):
    async with factory.begin() as s:
        await s.execute(
            text(
                "INSERT INTO todos (id, user_id, title, status, date_key, created_at, tags,"
                " recurrence_rule) VALUES ('todo_chat_base', :u, '매일', 'not-start',"
                " '2026-11-10', now(), '{}', '{\"unit\": \"day\", \"interval\": 1}')"
            ),
            {"u": _USER},
        )
        slot = "todo_chat_base::2026-11-16"
        move = ToolCall(
            "propose_moves", {"summary": "s", "items": [{"todo_id": slot, "date": "2026-11-18"}]}
        )
        model = _ScriptedModel([ModelTurn(text=None, calls=(move,)), ModelTurn(text="ok")])
        _, outcome, _, _ = await _turn_with_move(s, model)
        # 제안 뒤 사용자가 그 회차를 따로 옮겨 둠(예외 row)
        await _todo_port(s).apply_patch(_USER, slot, {"date_key": "2026-11-20"})
        with pytest.raises(AiProposalStaleException):
            await _proposals(s).apply(_USER, outcome.proposal_ids[0], None)
