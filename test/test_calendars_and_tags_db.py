"""사용자 캘린더와 태그 관리 — 실제 Postgres(최신 마이그레이션)에서.

- 기본 캘린더는 목록 조회 때 없으면 만들어진다. 캘린더를 지우면 그 할 일은 기본 캘린더(NULL)로.
- 다른 사용자의 캘린더 id 로 할 일을 만들 수 없다.
- 태그 이름 바꾸기는 모든 할 일의 tags 를 함께 고치고, 이미 있는 이름이면 합친다.
- 태그 삭제는 할 일에서 태그만 뺀다.

TEST_DATABASE_URL 의 DB 는 head 까지 마이그레이션돼 있어야 한다.
"""
import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.shared.infrastructure.database.models  # noqa: F401  (FK 대상 테이블 등록)
from app.calendars.application.use_cases.calendars import (
    CreateCalendarUseCase,
    DeleteCalendarUseCase,
    ListCalendarsUseCase,
)
from app.calendars.domain.exceptions.exceptions import (
    CalendarDefaultUndeletableException,
    CalendarNotFoundException,
)
from app.calendars.infrastructure.persistence.repositories.calendar_repo import CalendarRepository
from app.todo.application.dtos.commands import CreateTodoCommand
from app.todo.application.use_cases.create_todo import CreateTodoUseCase
from app.todo.application.use_cases.manage_tags import (
    DeleteTagUseCase,
    ListTagsUseCase,
    ReorderTagsUseCase,
    UpdateTagCommand,
    UpdateTagUseCase,
)
from app.todo.domain.exceptions.exceptions import TagNotFoundException
from app.todo.infrastructure.persistence.repositories.todo_repo import TodoRepository
from app.todo.infrastructure.persistence.repositories.user_tag_repo import UserTagRepository

_TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://ADMIN:heijiADMIN20090220!@localhost:5437/archive",
)
_USERS = ("usr_redesign_cal_a", "usr_redesign_cal_b")


class _NoSettings:
    async def find_by_user_id(self, user_id):
        return None


class _Queue:
    def __init__(self) -> None:
        self.items: list[str] = []

    async def enqueue(self, entity_type, entity_id, user_id):
        self.items.append(entity_id)


@pytest.fixture
async def factory():
    engine = create_async_engine(_TEST_DB_URL)
    f = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with f.begin() as s:
            has_table = await s.scalar(text("SELECT to_regclass('public.calendars')"))
        if has_table is None:
            pytest.skip("TEST_DATABASE_URL 의 DB 가 최신 마이그레이션이 아니다")
    except OSError:
        pytest.skip("test DB unavailable")
    async with f.begin() as s:
        for uid in _USERS:
            await s.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
            await s.execute(
                text(
                    "INSERT INTO users (id, email, created_at, country, timezone)"
                    " VALUES (:id, :email, now(), 'KR', 'Asia/Seoul')"
                ),
                {"id": uid, "email": f"{uid}@example.invalid"},
            )
    yield f
    async with f.begin() as s:
        for uid in _USERS:
            await s.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
    await engine.dispose()


async def _create_todo(session, user_id, title, tags=(), calendar_id=None):
    uc = CreateTodoUseCase(
        TodoRepository(session), _NoSettings(), CalendarRepository(session)  # type: ignore[arg-type]
    )
    return await uc.execute(
        CreateTodoCommand(
            user_id=user_id,
            title=title,
            date_key="2026-11-16",
            tags=list(tags),
            calendar_id=calendar_id,
        )
    )


async def test_calendar_lifecycle(factory):
    a, b = _USERS
    async with factory.begin() as s:
        repo = CalendarRepository(s)
        cals = await ListCalendarsUseCase(repo).execute(a)
        assert [(c.name, c.is_default, c.push_to_google) for c in cals] == [
            ("default", True, True)
        ]
        team = await CreateCalendarUseCase(repo).execute(a, "팀", "c3")
        todo = await _create_todo(s, a, "회의", calendar_id=team.id)
        assert todo.calendar_id == team.id

        # 다른 사용자의 캘린더 id 로는 만들 수 없다
        with pytest.raises(CalendarNotFoundException):
            await _create_todo(s, b, "남의 캘린더", calendar_id=team.id)

        with pytest.raises(CalendarDefaultUndeletableException):
            await DeleteCalendarUseCase(repo).execute(a, cals[0].id)

        await DeleteCalendarUseCase(repo).execute(a, team.id)

    async with factory.begin() as s:
        moved = await TodoRepository(s).find_by_id(todo.id, a)
        assert moved.calendar_id is None  # 기본 캘린더로


async def test_tag_rename_merge_reorder_and_delete(factory):
    a, b = _USERS
    async with factory.begin() as s:
        t1 = await _create_todo(s, a, "1", tags=["work", "urgent"])
        t2 = await _create_todo(s, a, "2", tags=["job"])
        await _create_todo(s, a, "3", tags=["work"])
        await _create_todo(s, b, "남의 할 일", tags=["work"])

    async with factory.begin() as s:
        todo_repo, tag_repo, queue = TodoRepository(s), UserTagRepository(s), _Queue()
        tags = await ListTagsUseCase(todo_repo, tag_repo).execute(a)
        assert {(t.name, t.count) for t in tags} == {("work", 2), ("urgent", 1), ("job", 1)}

        # 색 지정 후, job → work 로 이름 바꾸기 = 합치기
        upd = UpdateTagUseCase(todo_repo, tag_repo, queue)
        await upd.execute(UpdateTagCommand(user_id=a, name="work", color="c2"))
        merged = await upd.execute(UpdateTagCommand(user_id=a, name="job", new_name="work"))
        assert (merged.name, merged.count, merged.color) == ("work", 3, "c2")
        assert queue.items == [t2.id]

        await ReorderTagsUseCase(tag_repo).execute(a, ["urgent", "work"])
        ordered = await ListTagsUseCase(todo_repo, tag_repo).execute(a)
        assert [(t.name, t.sort_order) for t in ordered] == [("urgent", 0), ("work", 1)]

        await DeleteTagUseCase(todo_repo, tag_repo, queue).execute(a, "urgent")
        assert (await todo_repo.find_by_id(t1.id, a)).tags == ["work"]
        with pytest.raises(TagNotFoundException):
            await DeleteTagUseCase(todo_repo, tag_repo, queue).execute(a, "urgent")

        # 다른 사용자의 태그는 그대로
        assert (await todo_repo.tag_counts(b)) == {"work": 1}


async def test_rename_unknown_tag_is_404(factory):
    a, _ = _USERS
    async with factory.begin() as s:
        with pytest.raises(TagNotFoundException):
            await UpdateTagUseCase(
                TodoRepository(s), UserTagRepository(s), _Queue()
            ).execute(UpdateTagCommand(user_id=a, name="없는태그", color="c1"))



class _AutoPush:
    async def find_by_user_id(self, user_id):
        from types import SimpleNamespace

        return SimpleNamespace(calendar_auto_push_todo=True)


async def test_auto_push_only_for_calendars_that_push_to_google(factory):
    a, _ = _USERS
    async with factory.begin() as s:
        repo = CalendarRepository(s)
        await ListCalendarsUseCase(repo).execute(a)  # 기본 캘린더(push_to_google=True)
        study = await CreateCalendarUseCase(repo).execute(a, "스터디", "c5")  # 기본 False
        uc = CreateTodoUseCase(TodoRepository(s), _AutoPush(), repo)  # type: ignore[arg-type]
        on_default = await uc.execute(
            CreateTodoCommand(user_id=a, title="기본", date_key="2026-11-16")
        )
        on_study = await uc.execute(
            CreateTodoCommand(
                user_id=a, title="스터디", date_key="2026-11-16", calendar_id=study.id
            )
        )
        assert on_default.calendar_push_status == "pending"
        assert on_study.calendar_push_status is None


async def test_calendar_ids_filter_treats_null_as_default(factory):
    from app.todo.presentation.router import _filter_by_calendars

    a, _ = _USERS
    async with factory.begin() as s:
        repo = CalendarRepository(s)
        default = (await ListCalendarsUseCase(repo).execute(a))[0]
        team = await CreateCalendarUseCase(repo).execute(a, "팀", "c3")
        t_default = await _create_todo(s, a, "기본")
        t_team = await _create_todo(s, a, "팀", calendar_id=team.id)
        todos = [t_default, t_team]
        only_default = await _filter_by_calendars(repo, a, todos, default.id)
        both = await _filter_by_calendars(repo, a, todos, f"{default.id},{team.id}")
        assert [t.id for t in only_default] == [t_default.id]
        assert {t.id for t in both} == {t_default.id, t_team.id}
        assert await _filter_by_calendars(repo, a, todos, None) == todos


async def test_tag_router_passes_unset_for_omitted_fields():
    """색만 보내면 이름·순서는 '안 보냄'(공용 UNSET)이어야 한다 — 모듈별 sentinel 이 섞이면
    안 보낸 이름이 값으로 취급돼 엉뚱한 이름으로 바뀐다."""
    from types import SimpleNamespace

    from app.shared.domain.utils.unset import _Unset
    from app.todo.domain.models.user_tag import TagSummary
    from app.todo.presentation.requests.requests import UpdateTagRequest
    from app.todo.presentation.router import update_tag

    seen = {}

    class _Uc:
        async def execute(self, cmd):
            seen["cmd"] = cmd
            return TagSummary(name=cmd.name, count=0, color="c2", sort_order=None)

    body = UpdateTagRequest.model_validate({"color": "c2"})
    await update_tag("work", body, _Uc(), SimpleNamespace(id="usr_1"))  # type: ignore[arg-type]
    cmd = seen["cmd"]
    assert isinstance(cmd.new_name, _Unset) and isinstance(cmd.sort_order, _Unset)
    assert cmd.color == "c2"


async def test_ensure_default_is_idempotent_under_concurrency(factory):
    import asyncio

    a, _ = _USERS

    async def first_list():
        async with factory.begin() as s:
            return await ListCalendarsUseCase(CalendarRepository(s)).execute(a)

    results = await asyncio.gather(first_list(), first_list(), first_list())
    assert all(len(r) == 1 and r[0].is_default for r in results)
    assert len({r[0].id for r in results}) == 1


async def test_tag_count_counts_series_once_and_filtered_mode_filters_in_sql(factory):
    a, _ = _USERS
    async with factory.begin() as s:
        repo = TodoRepository(s)
        cal_repo = CalendarRepository(s)
        default = (await ListCalendarsUseCase(cal_repo).execute(a))[0]
        team = await CreateCalendarUseCase(cal_repo).execute(a, "팀2", "c4")
        base = await _create_todo(s, a, "반복", tags=["habit"])
        await s.execute(
            text(
                "INSERT INTO todos (id, user_id, title, status, date_key, created_at, tags,"
                " series_id, original_date_key)"
                " VALUES ('todo_exc_1', :u, '회차', 'done', '2026-11-17', now(), '{habit}',"
                " :base, '2026-11-17')"
            ),
            {"u": a, "base": base.id},
        )
        assert (await repo.tag_counts(a))["habit"] == 1  # 예외 row 가 있어도 시리즈는 base 한 건

        await _create_todo(s, a, "팀 지난 일", calendar_id=team.id)
        await s.execute(text("UPDATE todos SET date_key='2026-11-01' WHERE user_id=:u"), {"u": a})
        only_team = await repo.find_filtered(
            a, overdue_before="2026-11-16", calendar_ids=[team.id], limit=1
        )
        assert [t.calendar_id for t in only_team] == [team.id]
        with_default = await repo.find_filtered(
            a, overdue_before="2026-11-16", calendar_ids=[default.id],
            include_default_calendar=True, limit=50,
        )
        assert all(t.calendar_id is None for t in with_default) and with_default
