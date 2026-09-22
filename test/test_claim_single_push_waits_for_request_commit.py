"""즉시 push claim 이 요청 트랜잭션 커밋을 기다렸다가 claim 하는지.

버그: 라우터는 요청 트랜잭션 커밋 전에 push task 를 enqueue 한다. 워커가 그 사이
claim_single_pending_push 를 실행하면 행은 요청 txn 에 잠겨 있고 스냅샷상 아직
'pending' 이 아니어서 0행 → 즉시 push 가 no-op 이 되고 배치 주기(수 분)까지 밀렸다.
(FOR UPDATE 로만 바꿔도 상태 필터에서 먼저 탈락해 대기하지 않는다 — 실측.)

실제 Postgres(dev docker-compose 스택, localhost:5437)에 대해 두 세션으로 재현하는
통합 테스트 — fake 로는 행 잠금/스냅샷 동작을 재현할 수 없다.

실행:
    .venv/bin/python -m pytest test/test_claim_single_push_waits_for_request_commit.py -v
"""
import asyncio
import os
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_cancelled_exception_list_exclusion import _TEST_DB_URL as _DEFAULT_DB_URL

from app.shared.domain.utils.id import generate_id
from app.todo.domain.models.todo import Todo
from app.todo.domain.models.value_objects import TaskStatus
from app.todo.infrastructure.persistence.repositories.todo_repo import TodoRepository
from app.user.infrastructure.persistence.models.user_model import UserModel  # noqa: F401

_TEST_DB_URL = os.environ.get("TEST_DATABASE_URL", _DEFAULT_DB_URL)
_USER = "test_user_claim_single_push"


class _Db:
    def __init__(self) -> None:
        self.engine = create_async_engine(_TEST_DB_URL)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def setup(self) -> str:
        """테스트 유저 + 'synced' 상태 연동 todo 1건 생성 후 todo id 반환."""
        async with self.factory.begin() as s:
            await s.execute(text("DELETE FROM users WHERE id = :id"), {"id": _USER})
            await s.execute(
                text(
                    "INSERT INTO users (id, email, created_at, country, timezone, account_type)"
                    " VALUES (:id, :email, now(), 'US', 'UTC', 'user')"
                ),
                {"id": _USER, "email": "test-claim-single-push+ci@example.invalid"},
            )
            now = datetime.now(timezone.utc)
            todo = Todo(
                id=generate_id("todo"),
                user_id=_USER,
                title="claim test",
                status=TaskStatus.NOT_START,
                date_key="2026-09-22",
                created_at=now,
                updated_at=now,
            )
            await TodoRepository(s).save(todo)
            await s.execute(
                text(
                    "UPDATE todos SET calendar_push_status='synced', google_event_id='g1'"
                    " WHERE id = :id"
                ),
                {"id": todo.id},
            )
        return todo.id

    async def status(self, todo_id: str) -> str | None:
        async with self.factory() as s:
            return (
                await s.execute(
                    text("SELECT calendar_push_status FROM todos WHERE id = :id"), {"id": todo_id}
                )
            ).scalar()

    async def aclose(self) -> None:
        try:
            async with self.factory.begin() as s:
                await s.execute(text("DELETE FROM users WHERE id = :id"), {"id": _USER})
        finally:
            await self.engine.dispose()


async def _claim(db: _Db, todo_id: str) -> Todo | None:
    async with db.factory.begin() as s:
        return await TodoRepository(s).claim_single_pending_push(todo_id, _USER, "att_1")


async def _request_then(db: _Db, todo_id: str, *, commit: bool) -> Todo | None:
    """요청 txn 이 mark_for_push 후 커밋 전인 동안 claim 을 시작하고, 이후 커밋/롤백."""
    request = db.factory()
    try:
        await request.begin()
        await TodoRepository(request).mark_for_push(todo_id, _USER)
        claim_task = asyncio.create_task(_claim(db, todo_id))
        await asyncio.sleep(0.5)
        assert not claim_task.done(), "claim 이 요청 커밋을 기다리지 않고 끝남"
        if commit:
            await request.commit()
        else:
            await request.rollback()
        return await asyncio.wait_for(claim_task, timeout=5)
    finally:
        await request.close()


async def test_claim_waits_for_request_commit_then_claims() -> None:
    db = _Db()
    try:
        todo_id = await db.setup()
        claimed = await _request_then(db, todo_id, commit=True)
        assert claimed is not None and claimed.id == todo_id
        assert claimed.sync_attempt_id == "att_1"
        assert await db.status(todo_id) == "syncing"
    finally:
        await db.aclose()


async def test_claim_is_noop_when_request_rolls_back() -> None:
    db = _Db()
    try:
        todo_id = await db.setup()
        claimed = await _request_then(db, todo_id, commit=False)
        assert claimed is None
        assert await db.status(todo_id) == "synced"
    finally:
        await db.aclose()


async def test_claim_without_contention_is_immediate() -> None:
    db = _Db()
    try:
        todo_id = await db.setup()
        async with db.factory.begin() as s:
            await TodoRepository(s).mark_for_push(todo_id, _USER)
        claimed = await _claim(db, todo_id)
        assert claimed is not None
        assert await _claim(db, todo_id) is None  # 이미 syncing → 재claim 안 됨
    finally:
        await db.aclose()
