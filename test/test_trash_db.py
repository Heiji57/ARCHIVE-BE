"""휴지통(6단계) — 실제 Postgres(최신 마이그레이션)에서.

- 지운 할 일·회고는 조회(범위·통계·태그·검색·매칭)에서 빠지고, 되살리면 다시 나온다.
- 시리즈 전체 삭제는 base 와 예외 row 가 함께 들어가고 함께 나온다.
- 되살린 할 일은 Google 연동 흔적이 비고, 자동 보내기 조건이면 다시 push 대상.
- 같은 날 새 회고가 있으면 되살릴 수 없다(409). 폴더를 지우면 안의 회고가 휴지통으로.
- 영구 삭제는 청크·임베딩까지. 다른 사용자 것은 건드리지 못한다.
"""

import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.shared.infrastructure.database.models  # noqa: F401  (FK 대상 테이블 등록)
from app.calendars.infrastructure.persistence.repositories.calendar_repo import CalendarRepository
from app.data.application.use_cases.trash import TrashUseCase
from app.data.domain.exceptions.exceptions import (
    TrashItemNotFoundException,
    TrashKindInvalidException,
)
from app.retrospective.application.dtos.folder_commands import DeleteFolderCommand
from app.retrospective.application.use_cases.delete_entry import DeleteEntryUseCase
from app.retrospective.application.use_cases.delete_folder import DeleteFolderUseCase
from app.retrospective.application.use_cases.entry_trash import EntryTrashUseCase
from app.retrospective.domain.exceptions.exceptions import JournalEntryAlreadyExistsException
from app.retrospective.infrastructure.persistence.repositories.folder_repo import FolderRepository
from app.retrospective.infrastructure.persistence.repositories.journal_entry_repo import (
    JournalEntryRepository,
)
from app.todo.application.use_cases.delete_todo import DeleteTodoUseCase
from app.todo.application.use_cases.trash import TodoTrashUseCase
from app.todo.infrastructure.persistence.repositories.todo_repo import TodoRepository
from app.topic.infrastructure.persistence.repositories.chunk_repo import (
    EntryChunkRepository,
    TodoEmbeddingRepository,
)

_TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://ADMIN:heijiADMIN20090220!@localhost:5437/archive",
)
_A, _B = "usr_redesign_trash_a", "usr_redesign_trash_b"
_VEC = "[" + ",".join(["0.1"] * 768) + "]"


class _Settings:
    def __init__(self, auto_push: bool) -> None:
        self.auto_push = auto_push

    async def find_by_user_id(self, user_id):
        class S:
            calendar_auto_push_todo = self.auto_push

        return S()


@pytest.fixture
async def factory():
    engine = create_async_engine(_TEST_DB_URL)
    f = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with f.begin() as s:
            col = await s.scalar(
                text(
                    "SELECT 1 FROM information_schema.columns"
                    " WHERE table_name='todos' AND column_name='deleted_at'"
                )
            )
        if col is None:
            pytest.skip("TEST_DATABASE_URL 의 DB 가 최신 마이그레이션이 아니다")
    except OSError:
        pytest.skip("test DB unavailable")
    async with f.begin() as s:
        for uid in (_A, _B):
            await s.execute(text("DELETE FROM topic_entry_chunks WHERE user_id = :id"), {"id": uid})
            await s.execute(
                text("DELETE FROM topic_todo_embeddings WHERE user_id = :id"), {"id": uid}
            )
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
        for uid in (_A, _B):
            await s.execute(text("DELETE FROM topic_entry_chunks WHERE user_id = :id"), {"id": uid})
            await s.execute(
                text("DELETE FROM topic_todo_embeddings WHERE user_id = :id"), {"id": uid}
            )
            await s.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
    await engine.dispose()


async def _todo(s, tid, user=_A, **kw):
    cols = {
        "id": tid,
        "user_id": user,
        "title": kw.get("title", "할 일 " + tid),
        "status": kw.get("status", "not-start"),
        "date_key": kw.get("date_key", "2026-11-16"),
        "tags": kw.get("tags", []),
        "recurrence_rule": kw.get("rule"),
        "series_id": kw.get("series_id"),
        "original_date_key": kw.get("original_date_key"),
        "google_event_id": kw.get("gid"),
        "push_status": "synced" if kw.get("gid") else None,
    }
    await s.execute(
        text(
            "INSERT INTO todos (id, user_id, title, status, date_key, tags, recurrence_rule,"
            " series_id, original_date_key, google_event_id, calendar_push_status, created_at)"
            " VALUES (:id, :user_id, :title, :status, :date_key, :tags,"
            " CAST(:recurrence_rule AS jsonb), :series_id, :original_date_key, :google_event_id,"
            " :push_status, now())"
        ),
        cols,
    )


async def _entry(s, eid, date_key="2026-11-16", folder_id=None, user=_A):
    await s.execute(
        text(
            "INSERT INTO journal_entries (id, user_id, date_key, title, content, retro_type,"
            " folder_id, created_at) VALUES (:id, :u, :d, :t, '본문 휴지통', 'daily', :f, now())"
        ),
        {"id": eid, "u": user, "d": date_key, "t": "회고 " + eid, "f": folder_id},
    )


def _trash(s, auto_push=False) -> TrashUseCase:
    todos = TodoTrashUseCase(
        TodoRepository(s), _Settings(auto_push), CalendarRepository(s), TodoEmbeddingRepository(s)
    )
    entries = EntryTrashUseCase(JournalEntryRepository(s), EntryChunkRepository(s))
    return TrashUseCase(todos, entries)


async def test_trashed_todo_disappears_from_every_query_and_comes_back(factory):
    async with factory.begin() as s:
        await _todo(s, "todo_tr_1", tags=["운동"], title="휴지통 조깅")
        repo = TodoRepository(s)
        await DeleteTodoUseCase(repo).execute("todo_tr_1", _A)

        assert await repo.find_by_id("todo_tr_1", _A) is None
        assert await repo.find_by_date_range(_A, "2026-11-01", "2026-11-30") == []
        assert (await repo.find_by_full_text(_A, "조깅", 1, 10))[1] == 0
        assert "운동" not in await repo.tag_counts(_A)
        assert await repo.search_tags(_A, "운", 10) == []
        stats = await repo.get_todo_stats(
            _A, "2026-11-01", "2026-11-30", "2026-11-16", "2026-11-22", "Asia/Seoul"
        )
        assert stats.total == 0

        items, total = await _trash(s).list(_A, None, 1, 20)
        assert total == 1 and items[0].kind == "todo" and items[0].title == "휴지통 조깅"
        assert items[0].purge_at - items[0].deleted_at == timedelta(days=30)

        await _trash(s).restore(_A, "todo", "todo_tr_1")
        assert await repo.find_by_id("todo_tr_1", _A) is not None
        assert (await _trash(s).list(_A, None, 1, 20))[1] == 0


async def test_series_trashed_and_restored_together_with_calendar_reset(factory):
    rule = '{"unit": "day", "interval": 1}'
    async with factory.begin() as s:
        await _todo(s, "todo_tr_base", rule=rule, gid="gcal_base")
        await _todo(
            s,
            "todo_tr_exc",
            series_id="todo_tr_base",
            original_date_key="2026-11-17",
            date_key="2026-11-17",
        )
        repo = TodoRepository(s)
        outcome = await DeleteTodoUseCase(repo).execute("todo_tr_base", _A, "all")
        assert outcome.delete_google_event_id == "gcal_base"
        assert await repo.find_all_exceptions("todo_tr_base", _A) == []
        items, total = await _trash(s).list(_A, "todo", 1, 20)
        assert total == 1 and items[0].id == "todo_tr_base"  # 시리즈는 base 한 건

        result = await _trash(s, auto_push=True).restore(_A, "todo", "todo_tr_base")
        assert result.push_todo_id == "todo_tr_base" and result.reembed_todo_id is None
        base = await repo.find_by_id("todo_tr_base", _A)
        assert base is not None and base.google_event_id is None
        assert base.calendar_push_status == "pending"
        assert len(await repo.find_all_exceptions("todo_tr_base", _A)) == 1


async def test_entry_trash_hides_chunks_restore_conflict_and_purge(factory):
    async with factory.begin() as s:
        await _entry(s, "ent_tr_1")
        await s.execute(
            text(
                "INSERT INTO topic_entry_chunks (id, entry_id, user_id, chunk_index, text,"
                " date_key, embedding, created_at) VALUES ('chk_tr_1', 'ent_tr_1', :u, 0, 'x',"
                " '2026-11-16', CAST(:v AS vector), now())"
            ),
            {"u": _A, "v": _VEC},
        )
        chunks = EntryChunkRepository(s)
        vec = [0.1] * 768
        assert await chunks.search_similar_entry_ids(_A, vec, None, 0.5, 10) == ["ent_tr_1"]

        entries = JournalEntryRepository(s)
        await DeleteEntryUseCase(entries).execute("ent_tr_1", _A)
        assert await entries.find_by_id("ent_tr_1", _A) is None
        assert await chunks.search_similar_entry_ids(_A, vec, None, 0.5, 10) == []
        assert await entries.id_exists("ent_tr_1")  # IDOR 가드는 휴지통도 센다

        # 같은 날 새 회고가 생기면 되살릴 수 없다
        await _entry(s, "ent_tr_2")
        with pytest.raises(JournalEntryAlreadyExistsException):
            async with s.begin_nested():
                await _trash(s).restore(_A, "entry", "ent_tr_1")

        await _trash(s).purge(_A, "entry", "ent_tr_1")
        left = await s.scalar(text("SELECT count(*) FROM topic_entry_chunks WHERE id='chk_tr_1'"))
        assert left == 0
        with pytest.raises(TrashItemNotFoundException):
            await _trash(s).purge(_A, "entry", "ent_tr_1")


async def test_folder_delete_trashes_its_entries_and_restore_goes_uncategorized(factory):
    async with factory.begin() as s:
        await s.execute(
            text(
                "INSERT INTO folders (id, user_id, name, created_at)"
                " VALUES ('fld_tr_1', :u, '폴더', now())"
            ),
            {"u": _A},
        )
        await _entry(s, "ent_tr_f", folder_id="fld_tr_1")
        await DeleteFolderUseCase(FolderRepository(s), JournalEntryRepository(s)).execute(
            DeleteFolderCommand(user_id=_A, folder_id="fld_tr_1")
        )
        entries = JournalEntryRepository(s)
        assert await entries.find_by_id("ent_tr_f", _A) is None
        await _trash(s).restore(_A, "entry", "ent_tr_f")
        restored = await entries.find_by_id("ent_tr_f", _A)
        assert restored is not None and restored.folder_id is None


async def test_other_users_trash_untouchable_and_expired_purge(factory):
    async with factory.begin() as s:
        await _todo(s, "todo_tr_b", user=_B)
        await TodoRepository(s).soft_delete("todo_tr_b", _B)
        with pytest.raises(TrashItemNotFoundException):
            await _trash(s).restore(_A, "todo", "todo_tr_b")
        with pytest.raises(TrashItemNotFoundException):
            await _trash(s).purge(_A, "todo", "todo_tr_b")
        with pytest.raises(TrashKindInvalidException):
            await _trash(s).list(_A, "folder", 1, 20)

        await _todo(s, "todo_tr_old")
        await s.execute(
            text(
                "INSERT INTO topic_todo_embeddings (id, todo_id, user_id, text, date_key, status,"
                " created_at) VALUES ('emb_tr_old', 'todo_tr_old', :u, 'x', '2026-11-16',"
                " 'not-start', now())"
            ),
            {"u": _A},
        )
        await s.execute(
            text("UPDATE todos SET deleted_at = :t WHERE id = 'todo_tr_old'"),
            {"t": datetime.now(UTC) - timedelta(days=31)},
        )
        removed = await _trash(s).purge_expired(datetime.now(UTC) - timedelta(days=30))
        assert removed >= 1
        gone = await s.scalar(text("SELECT count(*) FROM todos WHERE id='todo_tr_old'"))
        emb = await s.scalar(
            text("SELECT count(*) FROM topic_todo_embeddings WHERE id='emb_tr_old'")
        )
        still = await s.scalar(text("SELECT count(*) FROM todos WHERE id='todo_tr_b'"))
        assert (gone, emb, still) == (0, 0, 1)


async def test_entry_count_excludes_trash(factory):
    async with factory.begin() as s:
        await _entry(s, "ent_tr_c1", date_key="2026-11-14")
        await _entry(s, "ent_tr_c2", date_key="2026-11-15")
        entries = JournalEntryRepository(s)
        assert await entries.count_all_by_user_id(_A) == 2
        await entries.soft_delete("ent_tr_c1", _A)
        assert await entries.count_all_by_user_id(_A) == 1


async def test_push_finalize_after_trash_is_a_noop(factory):
    async with factory.begin() as s:
        await _todo(s, "todo_tr_push")
        await s.execute(
            text(
                "UPDATE todos SET calendar_push_status='syncing', sync_attempt_id='att_1'"
                " WHERE id='todo_tr_push'"
            )
        )
        repo = TodoRepository(s)
        await repo.soft_delete("todo_tr_push", _A)
        # 워커가 이미 claim 한 뒤 휴지통으로 — finalize 가 반영되지 않아 워커가 새 일정을 정리한다
        assert not await repo.finalize_push_success("todo_tr_push", _A, "att_1", "gcal_new")
