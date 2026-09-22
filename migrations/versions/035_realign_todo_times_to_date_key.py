"""realign drifted todo start/end times to date_key

기존엔 Todo.move_to 가 date_key 만 바꿔서(날짜 이동 PATCH), 시간 있는 todo 의
start_time/end_time 이 옛 날짜에 남은 row 가 생겼다. Google Calendar push 는 시간
이벤트를 start/end 로만 만들기 때문에 캘린더 이벤트도 옛 날짜에 남아 있다.

date_key(화면에 보이는 날짜)를 정답으로 보고, start(없으면 end)의 로컬 날짜
(todos.timezone, 없으면 UTC)와의 일수 차이만큼 start/end 를 로컬 벽시계 기준으로
평행이동한다 — Todo.move_to 와 같은 의미(DST 무관). 시리즈 base(date_key = 시리즈
시작일)와 CANCELLED 예외 row 는 제외한다.

GCal 연동 row 는 mark_for_push 와 같은 값으로 재push 예약 — 백그라운드 배치
(worker.sync_user_calendar → run_batch_push)가 이벤트를 새 날짜로 갱신한다.

Revision ID: 035
Revises: 034
Create Date: 2026-09-22
"""
from typing import Sequence, Union

from alembic import op

revision: str = "035"
down_revision: Union[str, None] = "034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 날짜 산술은 "timestamptz AT TIME ZONE tz"(→ 로컬 timestamp) 에서 일수를 더한 뒤 다시
# "AT TIME ZONE tz"(→ timestamptz) 로 되돌려 로컬 벽시계 시각을 유지한다.
REALIGN_SQL = """
WITH targets AS (
    SELECT
        id,
        COALESCE(timezone, 'UTC') AS tz,
        date_key::date
            - (COALESCE(start_time, end_time) AT TIME ZONE COALESCE(timezone, 'UTC'))::date
            AS delta_days,
        calendar_push_status IS NOT NULL
            AND push_intent IS DISTINCT FROM 'delete' AS re_push
    FROM todos
    WHERE COALESCE(start_time, end_time) IS NOT NULL
      AND NOT (recurrence_rule IS NOT NULL AND series_id IS NULL)
      AND status <> 'cancelled'
      AND date_key <> to_char(
          COALESCE(start_time, end_time) AT TIME ZONE COALESCE(timezone, 'UTC'), 'YYYY-MM-DD'
      )
)
UPDATE todos SET
    start_time = (todos.start_time AT TIME ZONE t.tz + make_interval(days => t.delta_days))
        AT TIME ZONE t.tz,
    end_time = (todos.end_time AT TIME ZONE t.tz + make_interval(days => t.delta_days))
        AT TIME ZONE t.tz,
    calendar_push_status = CASE WHEN t.re_push THEN 'pending' ELSE todos.calendar_push_status END,
    push_intent = CASE WHEN t.re_push THEN 'push' ELSE todos.push_intent END,
    push_retry_count = CASE WHEN t.re_push THEN 0 ELSE todos.push_retry_count END,
    sync_attempt_id = CASE WHEN t.re_push THEN NULL ELSE todos.sync_attempt_id END,
    push_started_at = CASE WHEN t.re_push THEN NULL ELSE todos.push_started_at END
FROM targets t
WHERE todos.id = t.id
"""


def upgrade() -> None:
    op.execute(REALIGN_SQL)


def downgrade() -> None:
    # 데이터 보정이라 되돌릴 원본 값이 없다(원래 어긋나 있던 시각은 버그의 산물) — no-op.
    pass
