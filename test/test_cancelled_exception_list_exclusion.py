"""회귀 테스트: status=CANCELLED exception row 가 todo 목록 응답에 노출되지 않는지 확인.

버그: recurrenceScope=this 삭제(DELETE /todos/{virtual_id})는 해당 슬롯을 status=CANCELLED
exception row 로 실체화한다(delete_todo.py::_cancel_slot). 이 row 는 DB 에는 남아있어야
하지만(idempotency, get_todos_by_range 의 반복 확장 skip 로직이 의존), 클라이언트에 노출되는
목록 응답에는 절대 포함되면 안 된다 — api.yaml 의 TodoStatus enum 에 "cancelled" 은 아예
없는 값이고, FE 는 이를 몰라 그대로 렌더링해버린다.

원인: TodoRepository.find_by_date_range / find_by_date_key (실제 DB row 를 직접 읽는
경로 — get_todos_by_range.py / get_todos_by_date.py 의 1단계 "일반 todo" 조회) 가 base row
는 걸러내면서 CANCELLED row 는 걸러내지 않았다. find_by_full_text 와 get_todo_stats 는
이미 `status != 'cancelled'` 필터를 갖고 있었음 — 동일 정책을 두 메서드에도 적용했다.

이 테스트는 실제 Postgres(dev docker-compose 스택, localhost:5437)에 대해 실행되는
통합 테스트다 — fake repo 로는 SQL 필터 누락을 재현할 수 없기 때문이다. 전용 테스트
유저를 만들고 끝나면 cascade delete 로 정리한다.

실행:
    .venv/bin/python -m pytest test/test_cancelled_exception_list_exclusion.py -v
    .venv/bin/python test/test_cancelled_exception_list_exclusion.py
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# 컨테이너 내부 DATABASE_URL(host=postgres)은 호스트에서 직접 실행할 때는 resolve 되지
# 않는다 — docker-compose 가 5437 로 포워딩하는 로컬 접속 DSN을 직접 구성한다.
_TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://ADMIN:heijiADMIN20090220!@localhost:5437/archive",
)

from app.shared.domain.utils.id import generate_id
from app.todo.application.dtos.queries import GetTodosByDateQuery, GetTodosByRangeQuery
from app.todo.application.use_cases.delete_todo import DeleteTodoUseCase
from app.todo.application.use_cases.get_todos_by_date import GetTodosByDateUseCase
from app.todo.application.use_cases.get_todos_by_range import GetTodosByRangeUseCase
from app.todo.domain.models.todo import RecurrenceRule, Todo
from app.todo.domain.models.value_objects import TaskStatus
from app.todo.infrastructure.persistence.repositories.todo_repo import TodoRepository
# users.id 를 참조하는 FK(ForeignKey("users.id"))가 SQLAlchemy MetaData 에서 resolve
# 되려면 UserModel 이 import 되어 Base.metadata 에 users 테이블이 등록돼 있어야 한다
# — todo 모듈만 import 하면 이 스크립트가 직접 실행될 때 매핑 에러가 난다.
from app.user.infrastructure.persistence.models.user_model import UserModel  # noqa: F401

_TEST_USER_ID = "test_user_cancelled_leak"
_TEST_USER_EMAIL = "test-cancelled-leak+ci@example.invalid"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class _Db:
    """pytest-asyncio 는 테스트 함수마다 새 이벤트 루프를 쓸 수 있어(function-scoped),
    asyncpg 커넥션 풀을 모듈 레벨에서 한 번만 만들면 루프가 바뀐 다음 테스트에서
    "another operation is in progress" 로 깨진다. 테스트마다 엔진을 새로 만들고
    끝나면 dispose 한다."""

    def __init__(self) -> None:
        self.engine = create_async_engine(_TEST_DB_URL)
        self.session: AsyncSession = async_sessionmaker(self.engine, expire_on_commit=False)()

    async def setup_user(self) -> None:
        # 이미 존재하면(이전 실행이 정리에 실패한 경우) 지우고 다시 만든다.
        await self.session.execute(text("DELETE FROM users WHERE id = :id"), {"id": _TEST_USER_ID})
        await self.session.execute(
            text(
                "INSERT INTO users (id, email, created_at, country, timezone, account_type)"
                " VALUES (:id, :email, now(), 'US', 'UTC', 'user')"
            ),
            {"id": _TEST_USER_ID, "email": _TEST_USER_EMAIL},
        )
        await self.session.commit()

    async def aclose(self) -> None:
        try:
            # ON DELETE CASCADE 로 todos 도 함께 정리된다.
            await self.session.execute(text("DELETE FROM users WHERE id = :id"), {"id": _TEST_USER_ID})
            await self.session.commit()
        finally:
            await self.session.close()
            await self.engine.dispose()


def _master(date_key: str = "2026-08-01") -> Todo:
    return Todo(
        id=generate_id("todo"),
        user_id=_TEST_USER_ID,
        title="Daily standup (test)",
        status=TaskStatus.NOT_START,
        date_key=date_key,
        created_at=_now(),
        recurrence_rule=RecurrenceRule(unit="day", interval=1, until=None),
        tags=["test"],
    )


# ── (1) scope=this 삭제 후 GET /todos?from&to 스타일 range 조회 ───────────────
async def test_cancelled_slot_excluded_from_range_list():
    db = _Db()
    try:
        await db.setup_user()
        repo = TodoRepository(db.session)

        master = _master()
        await repo.save(master)
        await db.session.commit()

        delete_uc = DeleteTodoUseCase(repo)
        outcome = await delete_uc.execute(
            todo_id=f"{master.id}::2026-08-06", user_id=_TEST_USER_ID, recurrence_scope="this"
        )
        await db.session.commit()
        assert outcome.delete_google_event_id is None  # 캘린더 미연동

        # 삭제된 슬롯이 실제로 CANCELLED exception 으로 실체화됐는지 DB 레벨에서 확인.
        row = (
            await db.session.execute(
                text(
                    "SELECT status FROM todos WHERE series_id = :sid AND original_date_key = :od"
                ),
                {"sid": master.id, "od": "2026-08-06"},
            )
        ).first()
        assert row is not None, "CANCELLED exception row 가 DB 에 없다 — idempotency 깨짐"
        assert row.status == "cancelled"

        by_range_uc = GetTodosByRangeUseCase(repo)
        todos = await by_range_uc.execute(
            GetTodosByRangeQuery(user_id=_TEST_USER_ID, from_date="2026-08-01", to_date="2026-08-10")
        )
        slot_dates_08_06 = [t for t in todos if t.date_key == "2026-08-06"]
        assert slot_dates_08_06 == [], (
            f"CANCELLED 슬롯이 range 목록에 그대로 노출됨: {slot_dates_08_06}"
        )
        # status=cancelled 인 row 는 어떤 형태로도 응답에 없어야 한다.
        assert all(t.status != TaskStatus.CANCELLED for t in todos)

        # 다른 슬롯(08-07)은 여전히 virtual 로 정상 노출돼야 한다.
        assert any(t.date_key == "2026-08-07" for t in todos)
    finally:
        await db.aclose()


# ── (2) 같은 취소 슬롯을 GET /todos?dateKey 스타일 단일 날짜 조회로도 확인 ─────
async def test_cancelled_slot_excluded_from_date_list():
    db = _Db()
    try:
        await db.setup_user()
        repo = TodoRepository(db.session)

        master = _master()
        await repo.save(master)
        await db.session.commit()

        delete_uc = DeleteTodoUseCase(repo)
        await delete_uc.execute(
            todo_id=f"{master.id}::2026-08-06", user_id=_TEST_USER_ID, recurrence_scope="this"
        )
        await db.session.commit()

        by_date_uc = GetTodosByDateUseCase(repo)
        todos = await by_date_uc.execute(
            GetTodosByDateQuery(user_id=_TEST_USER_ID, date_key="2026-08-06")
        )
        assert todos == [], f"CANCELLED 슬롯이 dateKey 목록에 노출됨: {todos}"
    finally:
        await db.aclose()


# ── (3) PATCH 로 수정된(취소 아닌) exception row 는 여전히 정상 노출돼야 한다 ──
async def test_edited_non_cancelled_exception_still_listed():
    db = _Db()
    try:
        await db.setup_user()
        repo = TodoRepository(db.session)

        master = _master()
        await repo.save(master)
        await db.session.commit()

        edited = Todo(
            id=generate_id("todo"),
            user_id=_TEST_USER_ID,
            title="Daily standup (edited)",
            status=TaskStatus.IN_PROGRESS,
            date_key="2026-08-06",
            created_at=_now(),
            series_id=master.id,
            original_date_key="2026-08-06",
            tags=["test"],
        )
        await repo.upsert_exception(edited)
        await db.session.commit()

        by_range_uc = GetTodosByRangeUseCase(repo)
        todos = await by_range_uc.execute(
            GetTodosByRangeQuery(user_id=_TEST_USER_ID, from_date="2026-08-01", to_date="2026-08-10")
        )
        matches = [t for t in todos if t.date_key == "2026-08-06"]
        assert len(matches) == 1, f"수정된 exception row 개수가 예상과 다름: {matches}"
        assert matches[0].id == edited.id
        assert matches[0].status == TaskStatus.IN_PROGRESS
        assert matches[0].title == "Daily standup (edited)"
    finally:
        await db.aclose()


# ── (4) scope=following 삭제는 CANCELLED row 를 만들지 않고 recurrence_rule.until
#        만 truncate 한다 — 이 필터 변경으로 영향받지 않아야 한다 ─────────────────
async def test_following_scope_deletion_unaffected_by_filter():
    db = _Db()
    try:
        await db.setup_user()
        repo = TodoRepository(db.session)

        master = _master()
        await repo.save(master)
        await db.session.commit()

        delete_uc = DeleteTodoUseCase(repo)
        outcome = await delete_uc.execute(
            todo_id=f"{master.id}::2026-08-06", user_id=_TEST_USER_ID, recurrence_scope="following"
        )
        await db.session.commit()
        assert outcome.delete_google_event_id is None

        # following 은 CANCELLED row 를 만들지 않는다 — until 을 truncate 할 뿐.
        row = (
            await db.session.execute(
                text("SELECT status FROM todos WHERE series_id = :sid"),
                {"sid": master.id},
            )
        ).first()
        assert row is None, "following scope 가 예상과 달리 exception row 를 남김"

        refreshed = (
            await db.session.execute(
                text("SELECT recurrence_rule FROM todos WHERE id = :id"), {"id": master.id}
            )
        ).first()
        assert refreshed.recurrence_rule["until"] == "2026-08-05"

        # 08-06 이전 슬롯(08-01~08-05)은 여전히 virtual 로 정상 노출.
        by_range_uc = GetTodosByRangeUseCase(repo)
        todos = await by_range_uc.execute(
            GetTodosByRangeQuery(user_id=_TEST_USER_ID, from_date="2026-08-01", to_date="2026-08-10")
        )
        assert any(t.date_key == "2026-08-03" for t in todos)
        assert not any(t.date_key == "2026-08-06" for t in todos)
    finally:
        await db.aclose()


_TESTS = [
    test_cancelled_slot_excluded_from_range_list,
    test_cancelled_slot_excluded_from_date_list,
    test_edited_non_cancelled_exception_still_listed,
    test_following_scope_deletion_unaffected_by_filter,
]


async def _run_all() -> bool:
    ok = True
    for fn in _TESTS:
        try:
            await fn()
            print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            ok = False
            print(f"FAIL  {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001 — 스크립트 러너, 실패 원인 그대로 노출
            ok = False
            print(f"ERROR {fn.__name__}: {type(e).__name__}: {e}")
    return ok


if __name__ == "__main__":
    passed = asyncio.run(_run_all())
    sys.exit(0 if passed else 1)
