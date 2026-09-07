import json
import re
from datetime import datetime

from sqlalchemy import func, select, text
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession

from app.todo.domain.models.todo import RecurrenceRule, Todo
from app.todo.domain.models.value_objects import TaskStatus
from app.todo.domain.repositories.repository import (
    ITodoRepository,
    TagCount,
    TodoStatsRaw,
    WeeklyTrendDay,
)
from app.todo.infrastructure.persistence.models.todo_model import TodoModel

# claim(UPDATE todos ... FROM candidates ... RETURNING) 에서 Todo 엔티티 복원용 컬럼.
# candidates 도 id 를 가지므로 RETURNING 에서 반드시 todos. 로 한정(ambiguous 방지).
# 결과 컬럼 라벨은 한정자를 벗은 bare name 이라 _row_to_entity 의 by-name 접근과 호환.
_TODO_RETURNING = (
    "todos.id, todos.user_id, todos.title, todos.status, todos.date_key, "
    "todos.description, todos.start_time, todos.end_time, todos.timezone, "
    "todos.created_at, todos.updated_at, todos.completed_at, "
    "todos.calendar_push_status, todos.google_event_id, todos.push_intent, "
    "todos.push_started_at, todos.sync_attempt_id, todos.push_retry_count, "
    "todos.recurrence_rule, todos.series_id, todos.original_date_key, "
    "todos.original_start_time, todos.master_google_event_id, todos.tags, "
    "todos.due_date_key"
)

# base event 를 date_key 조회에서 제외하는 필터
# (recurrence_rule IS NOT NULL AND series_id IS NULL) → base row
_NOT_BASE_FILTER = "NOT (recurrence_rule IS NOT NULL AND series_id IS NULL)"


def _rule_to_dict(rule: RecurrenceRule | None) -> dict | None:
    if rule is None:
        return None
    return {"unit": rule.unit, "interval": rule.interval, "until": rule.until}


def _dict_to_rule(d: dict | None) -> RecurrenceRule | None:
    if d is None:
        return None
    return RecurrenceRule(unit=d["unit"], interval=d["interval"], until=d.get("until"))


# tsquery 구문에서 의미를 갖는 특수문자 — 사용자 입력에 그대로 있으면 문법 오류가 나므로
# 공백으로 치환해 제거한다. 남은 단어들에 접두(prefix) 연산자 :* 를 붙여 자동완성용
# tsquery 를 직접 조립한다(plainto_tsquery 는 완성된 단어만 매칭해 prefix 검색 불가).
_TSQUERY_SPECIAL_RE = re.compile(r"[&|!():<>*'\\]")


def _prefix_tsquery(raw: str) -> str | None:
    cleaned = _TSQUERY_SPECIAL_RE.sub(" ", raw)
    words = cleaned.split()
    if not words:
        return None
    return " & ".join(f"{w}:*" for w in words)


class TodoRepository(ITodoRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, todo: Todo) -> Todo:
        # _to_model 은 push 제어 컬럼을 설정하지 않는다 → merge 가 해당 컬럼을 건드리지
        # 않아(미설정 속성 skip) 워커의 push 진행 상태를 보존한다.
        model = self._to_model(todo)
        merged = await self._session.merge(model)
        await self._session.flush()
        return self._to_entity(merged)

    async def find_by_id(self, id: str, user_id: str) -> Todo | None:
        result = await self._session.execute(
            select(TodoModel).where(TodoModel.id == id, TodoModel.user_id == user_id)
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def find_by_date_range(self, user_id: str, from_date: str, to_date: str) -> list[Todo]:
        result = await self._session.execute(
            select(TodoModel)
            .where(
                TodoModel.user_id == user_id,
                TodoModel.date_key >= from_date,
                TodoModel.date_key <= to_date,
                # base event 는 반복 확장 로직에서 별도 처리 — 직접 노출 안 함
                text(_NOT_BASE_FILTER),
            )
            .order_by(TodoModel.date_key, TodoModel.created_at)
        )
        return [self._to_entity(m) for m in result.scalars()]

    async def find_by_date_key(self, user_id: str, date_key: str) -> list[Todo]:
        result = await self._session.execute(
            select(TodoModel)
            .where(
                TodoModel.user_id == user_id,
                TodoModel.date_key == date_key,
                text(_NOT_BASE_FILTER),
            )
            .order_by(TodoModel.created_at)
        )
        return [self._to_entity(m) for m in result.scalars()]

    async def find_by_full_text(
        self, user_id: str, query: str, page: int, size: int
    ) -> tuple[list[Todo], int]:
        stmt = (
            select(TodoModel)
            .where(
                TodoModel.user_id == user_id,
                # base event 제외, CANCELLED 예외 row 제외
                text(_NOT_BASE_FILTER),
                TodoModel.status != "cancelled",
            )
            .where(TodoModel.title_tsv.match(query))  # type: ignore[union-attr]
        )
        total = await self._session.scalar(
            select(func.count()).select_from(stmt.subquery())
        )
        result = await self._session.execute(
            stmt.order_by(TodoModel.created_at.desc()).offset((page - 1) * size).limit(size)
        )
        return [self._to_entity(m) for m in result.scalars()], total or 0

    async def delete(self, id: str, user_id: str) -> None:
        model = await self._session.execute(
            select(TodoModel).where(TodoModel.id == id, TodoModel.user_id == user_id)
        )
        row = model.scalar_one_or_none()
        if row:
            await self._session.delete(row)

    async def find_by_google_event_id(
        self, user_id: str, google_event_id: str
    ) -> Todo | None:
        result = await self._session.execute(
            text(
                f"SELECT {_TODO_RETURNING} FROM todos"
                " WHERE user_id=:user_id AND google_event_id=:google_event_id"
                " LIMIT 1"
            ),
            {"user_id": user_id, "google_event_id": google_event_id},
        )
        row = result.first()
        return self._row_to_entity(row) if row else None

    async def find_by_google_event_ids(
        self, user_id: str, google_event_ids: list[str]
    ) -> list[Todo]:
        if not google_event_ids:
            return []
        result = await self._session.execute(
            select(TodoModel).where(
                TodoModel.user_id == user_id,
                TodoModel.google_event_id.in_(set(google_event_ids)),
            )
        )
        return [self._to_entity(m) for m in result.scalars()]

    async def create_from_calendar_event(self, todo: Todo) -> Todo | None:
        # save()/_to_model() 은 push 제어 컬럼을 의도적으로 제외하므로, Google 원본
        # 이벤트를 이미-synced 상태의 Todo 로 최초 승격할 때는 이 전용 INSERT 를 쓴다.
        # ON CONFLICT: uq_todos_user_google_event (partial unique) — 동시 sync race 로
        # 다른 워커가 먼저 승격한 경우 조용히 skip (None 반환).
        result = await self._session.execute(
            text(
                "INSERT INTO todos ("
                "  id, user_id, title, status, date_key, description,"
                "  start_time, end_time, timezone, created_at, updated_at, completed_at,"
                "  calendar_push_status, google_event_id, push_intent, push_retry_count, tags"
                ") VALUES ("
                "  :id, :user_id, :title, :status, :date_key, :description,"
                "  :start_time, :end_time, :timezone, :created_at, :updated_at, :completed_at,"
                "  'synced', :google_event_id, NULL, 0, :tags"
                ") ON CONFLICT (user_id, google_event_id) WHERE google_event_id IS NOT NULL"
                "  DO NOTHING"
                f" RETURNING {_TODO_RETURNING}"
            ),
            {
                "id": todo.id,
                "user_id": todo.user_id,
                "title": todo.title,
                "status": todo.status.value,
                "date_key": todo.date_key,
                "description": todo.description,
                "start_time": todo.start_time,
                "end_time": todo.end_time,
                "timezone": todo.timezone,
                "created_at": todo.created_at,
                "updated_at": todo.updated_at,
                "completed_at": todo.completed_at,
                "google_event_id": todo.google_event_id,
                "tags": todo.tags,
            },
        )
        row = result.first()
        return self._row_to_entity(row) if row else None

    async def clear_calendar_link(self, todo_id: str, user_id: str) -> None:
        await self._session.execute(
            text(
                "UPDATE todos SET calendar_push_status=NULL, google_event_id=NULL, "
                "push_intent=NULL, push_started_at=NULL, sync_attempt_id=NULL, push_retry_count=0 "
                "WHERE id=:id AND user_id=:user_id"
            ),
            {"id": todo_id, "user_id": user_id},
        )

    # ── Calendar push 상태 관리 (타겟 SQL) ─────────────────────────────────────

    async def mark_for_push(self, todo_id: str, user_id: str) -> None:
        await self._session.execute(
            text(
                "UPDATE todos SET calendar_push_status='pending', push_intent='push', "
                "push_retry_count=0, sync_attempt_id=NULL, push_started_at=NULL "
                "WHERE id=:id AND user_id=:user_id"
            ),
            {"id": todo_id, "user_id": user_id},
        )

    async def mark_for_delete(self, todo_id: str, user_id: str) -> None:
        await self._session.execute(
            text(
                "UPDATE todos SET calendar_push_status='pending_delete', push_intent='delete', "
                "push_retry_count=0, sync_attempt_id=NULL, push_started_at=NULL "
                "WHERE id=:id AND user_id=:user_id"
            ),
            {"id": todo_id, "user_id": user_id},
        )

    async def claim_pending_pushes(
        self,
        user_id: str,
        attempt_id: str,
        max_retries: int,
        stuck_before: datetime,
        batch_size: int,
    ) -> list[Todo]:
        result = await self._session.execute(
            text(
                "WITH candidates AS ("
                "  SELECT id FROM todos"
                "  WHERE user_id = :user_id"
                "    AND calendar_push_status IN ('pending','pending_delete','failed','syncing')"
                "    AND push_retry_count < :max_retries"
                # v10: staleness 게이트는 'syncing' 에만 — pending/failed 등은 즉시 claim.
                "    AND (calendar_push_status <> 'syncing'"
                "         OR push_started_at IS NULL OR push_started_at < :stuck_before)"
                "  ORDER BY updated_at"
                "  LIMIT :batch_size"
                "  FOR UPDATE SKIP LOCKED"
                ")"
                " UPDATE todos SET calendar_push_status='syncing', push_started_at=now(),"
                "   sync_attempt_id=:attempt_id"
                " FROM candidates WHERE todos.id = candidates.id"
                f" RETURNING {_TODO_RETURNING}"
            ),
            {
                "user_id": user_id,
                "attempt_id": attempt_id,
                "max_retries": max_retries,
                "stuck_before": stuck_before,
                "batch_size": batch_size,
            },
        )
        return [self._row_to_entity(r) for r in result.all()]

    async def claim_single_pending_push(
        self, todo_id: str, user_id: str, attempt_id: str
    ) -> Todo | None:
        result = await self._session.execute(
            text(
                "WITH candidates AS ("
                "  SELECT id FROM todos"
                "  WHERE id = :id AND user_id = :user_id"
                "    AND calendar_push_status IN ('pending','pending_delete')"
                "  FOR UPDATE SKIP LOCKED"
                ")"
                " UPDATE todos SET calendar_push_status='syncing', push_started_at=now(),"
                "   sync_attempt_id=:attempt_id"
                " FROM candidates WHERE todos.id = candidates.id"
                f" RETURNING {_TODO_RETURNING}"
            ),
            {"id": todo_id, "user_id": user_id, "attempt_id": attempt_id},
        )
        row = result.first()
        return self._row_to_entity(row) if row else None

    async def heartbeat_push(self, todo_id: str, user_id: str, attempt_id: str) -> bool:
        result = await self._session.execute(
            text(
                "UPDATE todos SET push_started_at=now() "
                "WHERE id=:id AND user_id=:user_id AND sync_attempt_id=:attempt_id "
                "RETURNING id"
            ),
            {"id": todo_id, "user_id": user_id, "attempt_id": attempt_id},
        )
        return result.first() is not None

    async def finalize_push_success(
        self, todo_id: str, user_id: str, attempt_id: str, google_event_id: str
    ) -> bool:
        result = await self._session.execute(
            text(
                "UPDATE todos SET calendar_push_status='synced', google_event_id=:gid, "
                "push_intent=NULL, push_started_at=NULL, sync_attempt_id=NULL, push_retry_count=0 "
                "WHERE id=:id AND user_id=:user_id AND sync_attempt_id=:attempt_id "
                "RETURNING id"
            ),
            {"id": todo_id, "user_id": user_id, "attempt_id": attempt_id, "gid": google_event_id},
        )
        return result.first() is not None

    async def finalize_delete_success(
        self, todo_id: str, user_id: str, attempt_id: str
    ) -> bool:
        result = await self._session.execute(
            text(
                "UPDATE todos SET calendar_push_status=NULL, google_event_id=NULL, "
                "push_intent=NULL, push_started_at=NULL, sync_attempt_id=NULL, push_retry_count=0 "
                "WHERE id=:id AND user_id=:user_id AND sync_attempt_id=:attempt_id "
                "RETURNING id"
            ),
            {"id": todo_id, "user_id": user_id, "attempt_id": attempt_id},
        )
        return result.first() is not None

    async def finalize_push_failure(
        self, todo_id: str, user_id: str, attempt_id: str, retry_count: int
    ) -> bool:
        result = await self._session.execute(
            text(
                "UPDATE todos SET calendar_push_status='failed', push_started_at=NULL, "
                "sync_attempt_id=NULL, push_retry_count=:retry_count "
                "WHERE id=:id AND user_id=:user_id AND sync_attempt_id=:attempt_id "
                "RETURNING id"
            ),
            {"id": todo_id, "user_id": user_id, "attempt_id": attempt_id, "retry_count": retry_count},
        )
        return result.first() is not None

    async def bulk_clear_calendar_push(self, user_id: str) -> None:
        # google_event_id 는 의도적으로 보존한다 — calendar_push_status=NULL 이면
        # worker(claim 대상: pending/pending_delete/failed/syncing)가 어차피 이 todo 를
        # 절대 건드리지 않으므로 안전하고, 재연결 시 find_by_google_event_id 의 dedup
        # 키로 재사용돼 같은 이벤트가 중복 todo 로 재생성되는 것을 막는다.
        await self._session.execute(
            text(
                "UPDATE todos SET calendar_push_status=NULL, "
                "push_intent=NULL, push_started_at=NULL, sync_attempt_id=NULL, push_retry_count=0 "
                "WHERE user_id=:user_id AND calendar_push_status IS NOT NULL"
            ),
            {"user_id": user_id},
        )

    async def reset_failed_retry_counts(self, user_id: str) -> None:
        await self._session.execute(
            text(
                "UPDATE todos SET push_retry_count=0 "
                "WHERE user_id=:user_id AND calendar_push_status='failed'"
            ),
            {"user_id": user_id},
        )

    # ── 반복 Todo 전용 ──────────────────────────────────────────────────────────

    async def find_series_base(self, series_id: str, user_id: str) -> Todo | None:
        result = await self._session.execute(
            select(TodoModel).where(
                TodoModel.id == series_id,
                TodoModel.user_id == user_id,
                TodoModel.recurrence_rule.isnot(None),
                TodoModel.series_id.is_(None),
            )
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def find_masters_overlapping(
        self, user_id: str, from_date: str, to_date: str
    ) -> list[Todo]:
        """[from_date, to_date] 와 겹치는 반복 시리즈 base event 목록.

        겹침: base.date_key <= to_date AND (until IS NULL OR until >= from_date).
        JSONB ->>'until' 으로 until 필드 접근 (raw SQL).
        """
        result = await self._session.execute(
            text(
                "SELECT * FROM todos"
                " WHERE user_id = :user_id"
                "   AND recurrence_rule IS NOT NULL"
                "   AND series_id IS NULL"
                "   AND date_key <= :to_date"
                "   AND (recurrence_rule->>'until' IS NULL"
                "        OR recurrence_rule->>'until' >= :from_date)"
            ),
            {"user_id": user_id, "from_date": from_date, "to_date": to_date},
        )
        rows = result.mappings().all()
        return [self._mapping_to_entity(r) for r in rows]

    async def find_exceptions_batch(
        self, user_id: str, series_ids: list[str], from_date: str, to_date: str
    ) -> list[Todo]:
        """복수 시리즈의 exception row 를 1회 IN 조회로 가져온다."""
        if not series_ids:
            return []
        result = await self._session.execute(
            select(TodoModel).where(
                TodoModel.user_id == user_id,
                TodoModel.series_id.in_(series_ids),
                TodoModel.original_date_key >= from_date,
                TodoModel.original_date_key <= to_date,
            )
        )
        return [self._to_entity(m) for m in result.scalars()]

    async def find_all_exceptions(self, series_id: str, user_id: str) -> list[Todo]:
        result = await self._session.execute(
            select(TodoModel).where(
                TodoModel.series_id == series_id,
                TodoModel.user_id == user_id,
            )
        )
        return [self._to_entity(m) for m in result.scalars()]

    async def upsert_exception(self, todo: Todo) -> Todo:
        """exception row upsert.

        ON CONFLICT (series_id, original_date_key) WHERE series_id IS NOT NULL
        → 충돌 시 모든 콘텐츠 컬럼 UPDATE (push 컬럼 제외).
        """
        rule_json = json.dumps(_rule_to_dict(todo.recurrence_rule)) if todo.recurrence_rule else None
        result = await self._session.execute(
            text(
                "INSERT INTO todos ("
                "  id, user_id, title, status, date_key, description,"
                "  start_time, end_time, timezone, created_at, updated_at, completed_at,"
                "  recurrence_rule, series_id, original_date_key,"
                "  original_start_time, master_google_event_id, tags, due_date_key"
                ") VALUES ("
                "  :id, :user_id, :title, :status, :date_key, :description,"
                "  :start_time, :end_time, :timezone, :created_at, :updated_at, :completed_at,"
                "  CAST(:recurrence_rule AS jsonb), :series_id, :original_date_key,"
                "  :original_start_time, :master_google_event_id, :tags, :due_date_key"
                ") ON CONFLICT (series_id, original_date_key) WHERE series_id IS NOT NULL"
                " DO UPDATE SET"
                "  title=EXCLUDED.title, status=EXCLUDED.status, date_key=EXCLUDED.date_key,"
                "  description=EXCLUDED.description, start_time=EXCLUDED.start_time,"
                "  end_time=EXCLUDED.end_time, timezone=EXCLUDED.timezone,"
                "  updated_at=now(), completed_at=EXCLUDED.completed_at,"
                "  master_google_event_id=EXCLUDED.master_google_event_id,"
                "  tags=EXCLUDED.tags, due_date_key=EXCLUDED.due_date_key"
                f" RETURNING {_TODO_RETURNING}"
            ),
            {
                "id": todo.id,
                "user_id": todo.user_id,
                "title": todo.title,
                "status": todo.status.value,
                "date_key": todo.date_key,
                "description": todo.description,
                "start_time": todo.start_time,
                "end_time": todo.end_time,
                "timezone": todo.timezone,
                "created_at": todo.created_at,
                "updated_at": todo.updated_at,
                "completed_at": todo.completed_at,
                "recurrence_rule": rule_json,
                "series_id": todo.series_id,
                "original_date_key": todo.original_date_key,
                "original_start_time": todo.original_start_time,
                "master_google_event_id": todo.master_google_event_id,
                "tags": todo.tags,
                "due_date_key": todo.due_date_key,
            },
        )
        row = result.first()
        return self._row_to_entity(row)  # type: ignore[arg-type]

    async def delete_exceptions_from(
        self, series_id: str, user_id: str, from_date: str
    ) -> None:
        await self._session.execute(
            text(
                "DELETE FROM todos"
                " WHERE series_id=:series_id AND user_id=:user_id"
                "   AND original_date_key >= :from_date"
            ),
            {"series_id": series_id, "user_id": user_id, "from_date": from_date},
        )

    async def delete_all_exceptions(self, series_id: str, user_id: str) -> None:
        await self._session.execute(
            text(
                "DELETE FROM todos WHERE series_id=:series_id AND user_id=:user_id"
            ),
            {"series_id": series_id, "user_id": user_id},
        )

    # ── Mapping ────────────────────────────────────────────────────────────────

    def _to_model(self, entity: Todo) -> TodoModel:
        # push 제어 컬럼은 의도적으로 제외 — merge 가 해당 속성을 관리하지 않게 하여
        # 워커 push 상태를 보존한다(콘텐츠 save 와 push 상태 쓰기 분리).
        return TodoModel(
            id=entity.id,
            user_id=entity.user_id,
            title=entity.title,
            status=entity.status.value,
            date_key=entity.date_key,
            description=entity.description,
            start_time=entity.start_time,
            end_time=entity.end_time,
            timezone=entity.timezone,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
            completed_at=entity.completed_at,
            recurrence_rule=_rule_to_dict(entity.recurrence_rule),
            series_id=entity.series_id,
            original_date_key=entity.original_date_key,
            original_start_time=entity.original_start_time,
            master_google_event_id=entity.master_google_event_id,
            tags=entity.tags,
            due_date_key=entity.due_date_key,
        )

    def _to_entity(self, model: TodoModel) -> Todo:
        return Todo(
            id=model.id,
            user_id=model.user_id,
            title=model.title,
            status=TaskStatus(model.status),
            date_key=model.date_key,
            description=model.description,
            start_time=model.start_time,
            end_time=model.end_time,
            timezone=model.timezone,
            created_at=model.created_at,
            updated_at=model.updated_at,
            completed_at=model.completed_at,
            recurrence_rule=_dict_to_rule(model.recurrence_rule),
            series_id=model.series_id,
            original_date_key=model.original_date_key,
            original_start_time=model.original_start_time,
            master_google_event_id=model.master_google_event_id,
            calendar_push_status=model.calendar_push_status,
            google_event_id=model.google_event_id,
            push_intent=model.push_intent,
            push_started_at=model.push_started_at,
            sync_attempt_id=model.sync_attempt_id,
            push_retry_count=model.push_retry_count,
            tags=model.tags,
            due_date_key=model.due_date_key,
        )

    def _row_to_entity(self, row: Row) -> Todo:
        m = row._mapping
        raw_rule = m["recurrence_rule"]
        rule = _dict_to_rule(raw_rule) if raw_rule else None
        return Todo(
            id=m["id"],
            user_id=m["user_id"],
            title=m["title"],
            status=TaskStatus(m["status"]),
            date_key=m["date_key"],
            description=m["description"],
            start_time=m["start_time"],
            end_time=m["end_time"],
            timezone=m["timezone"],
            created_at=m["created_at"],
            updated_at=m["updated_at"],
            completed_at=m["completed_at"],
            recurrence_rule=rule,
            series_id=m["series_id"],
            original_date_key=m["original_date_key"],
            original_start_time=m["original_start_time"],
            master_google_event_id=m["master_google_event_id"],
            calendar_push_status=m["calendar_push_status"],
            google_event_id=m["google_event_id"],
            push_intent=m["push_intent"],
            push_started_at=m["push_started_at"],
            sync_attempt_id=m["sync_attempt_id"],
            push_retry_count=m["push_retry_count"],
            tags=list(m["tags"]) if m["tags"] is not None else [],
            due_date_key=m.get("due_date_key"),
        )

    def _mapping_to_entity(self, m: dict) -> Todo:
        """find_masters_overlapping 의 raw text() 결과 매핑용."""
        raw_rule = m.get("recurrence_rule")
        if isinstance(raw_rule, str):
            raw_rule = json.loads(raw_rule)
        rule = _dict_to_rule(raw_rule) if raw_rule else None
        return Todo(
            id=m["id"],
            user_id=m["user_id"],
            title=m["title"],
            status=TaskStatus(m["status"]),
            date_key=m["date_key"],
            description=m["description"],
            start_time=m["start_time"],
            end_time=m["end_time"],
            timezone=m["timezone"],
            created_at=m["created_at"],
            updated_at=m["updated_at"],
            completed_at=m.get("completed_at"),
            recurrence_rule=rule,
            series_id=m.get("series_id"),
            original_date_key=m.get("original_date_key"),
            original_start_time=m.get("original_start_time"),
            master_google_event_id=m.get("master_google_event_id"),
            calendar_push_status=m.get("calendar_push_status"),
            google_event_id=m.get("google_event_id"),
            push_intent=m.get("push_intent"),
            push_started_at=m.get("push_started_at"),
            sync_attempt_id=m.get("sync_attempt_id"),
            push_retry_count=m.get("push_retry_count") or 0,
            tags=list(m.get("tags") or []),
            due_date_key=m.get("due_date_key"),
        )

    # ── Stats ──────────────────────────────────────────────────────────────────

    async def get_todo_stats(
        self,
        user_id: str,
        range_from: str,
        range_to: str,
        week_from: str,
        week_to: str,
        tz: str,
    ) -> TodoStatsRaw:
        _NOT_BASE = "NOT (recurrence_rule IS NOT NULL AND series_id IS NULL)"

        # 1) 상태별 카운트 (range 기준) — cancelled 제외 (get_todos_by_date 와 동일 정책)
        status_rows = await self._session.execute(
            text(
                f"SELECT status, COUNT(*)::int AS cnt FROM todos"
                f" WHERE user_id=:user_id AND date_key BETWEEN :from_d AND :to_d"
                f" AND {_NOT_BASE} AND status != 'cancelled'"
                f" GROUP BY status"
            ),
            {"user_id": user_id, "from_d": range_from, "to_d": range_to},
        )
        total = done_count = in_progress_count = not_start_count = 0
        for row in status_rows:
            cnt = row.cnt
            total += cnt
            if row.status == "done":
                done_count = cnt
            elif row.status == "in-progress":
                in_progress_count = cnt
            elif row.status == "not-start":
                not_start_count = cnt

        # 2) tag 분포 (range 기준). 태그가 여러 개인 todo는 각 태그 버킷에 중복 집계된다.
        tag_rows = await self._session.execute(
            text(
                f"SELECT unnest(tags) AS tag, COUNT(*)::int AS cnt FROM todos"
                f" WHERE user_id=:user_id AND date_key BETWEEN :from_d AND :to_d"
                f" AND cardinality(tags) > 0 AND {_NOT_BASE} AND status != 'cancelled'"
                f" GROUP BY tag ORDER BY cnt DESC"
            ),
            {"user_id": user_id, "from_d": range_from, "to_d": range_to},
        )
        tag_distribution = [TagCount(tag=row.tag, count=row.cnt) for row in tag_rows]

        # 3) weekly_trend: 이번 ISO주, completed_at 로컬 날짜 기준
        trend_rows = await self._session.execute(
            text(
                f"SELECT (completed_at AT TIME ZONE :tz)::date::text AS local_date,"
                f"       COUNT(*)::int AS cnt"
                f" FROM todos"
                f" WHERE user_id=:user_id AND status='done'"
                f"   AND completed_at IS NOT NULL"
                f"   AND (completed_at AT TIME ZONE :tz)::date::text BETWEEN :wfrom AND :wto"
                f"   AND {_NOT_BASE}"
                f" GROUP BY local_date"
            ),
            {"user_id": user_id, "tz": tz, "wfrom": week_from, "wto": week_to},
        )
        weekly_trend = [
            WeeklyTrendDay(date_key=row.local_date, done_count=row.cnt)
            for row in trend_rows
        ]

        return TodoStatsRaw(
            total=total,
            done_count=done_count,
            in_progress_count=in_progress_count,
            not_start_count=not_start_count,
            weekly_trend=weekly_trend,
            tag_distribution=tag_distribution,
        )

    # ── 태그 자동완성 검색 ────────────────────────────────────────────────────────

    async def search_tags(self, user_id: str, query: str, limit: int) -> list[str]:
        tsquery = _prefix_tsquery(query)
        if tsquery is None:
            return []

        result = await self._session.execute(
            text(
                "SELECT tag, COUNT(*)::int AS cnt FROM todos, unnest(tags) AS tag"
                " WHERE user_id=:user_id"
                "   AND to_tsvector('simple', tag) @@ to_tsquery('simple', :tsquery)"
                " GROUP BY tag"
                " ORDER BY cnt DESC, tag ASC"
                " LIMIT :limit"
            ),
            {"user_id": user_id, "tsquery": tsquery, "limit": limit},
        )
        return [row.tag for row in result]
