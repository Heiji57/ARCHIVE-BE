"""반복 시리즈의 ARCHIVE until ↔ Google UNTIL 불일치 정리 (일회성 유지보수).

배경: `_update_following` 이 첫 회차 분리에서 옛 base 를 회차 0개(until < date_key)로
남기던 버그와, 단축된 RRULE 재push 가 2026-09-07(a7f536b) 에야 추가된 탓에, Google 에
종료일 없이 영원히 반복되는 옛 시리즈가 남아 매주 중복 일정이 뜬다.

분류와 조치:
  repush       ARCHIVE 와 Google UNTIL 이 다르고, Google 쪽에 **미래 회차가 남아있음**
               (UNTIL 없음 또는 오늘 이후) → mark_for_push. 워커가 올바른 UNTIL 로 갱신.
  repush-past  차이가 과거 구간에만 있음 → 기본 skip. 맞추면 Google 에 남은 과거 일정이
               지워지므로(기록 손실) --include-past 를 줄 때만 처리한다.
  stop-future  ARCHIVE 에선 끝난 시리즈(until < date_key)인데 Google 은 계속 반복,
               과거 회차가 있음 → Google RRULE 에 UNTIL=어제 를 직접 넣고 ARCHIVE
               연동 해제(과거 기록 보존, 미래 중복만 중단).
  delete       위와 같지만 시작일이 아직 미래라 보존할 과거가 없음 → 이벤트 삭제 후 연동 해제.
  ok           일치 — 건드리지 않음.

주의: Google 쓰기 → ARCHIVE 연동 해제는 원자적이지 않다. 그 사이에 중단되면 Google 은
고쳐졌지만 ARCHIVE row 는 연동 상태로 남는다(다음 실행은 "ok" 로 건너뜀). 그때는 해당
todo 의 calendar_push_status/google_event_id 를 수동으로 비워야 한다.

사용법 (기본 dry-run):
    DATABASE_URL=postgresql+asyncpg://user:pw@localhost:5437/archive \
        python scripts/fix_calendar_series_drift.py
    ... --apply      # 실제 반영 (Google 쓰기 포함)
"""
import argparse
import asyncio
import os
import sys
from datetime import date, datetime, timedelta, timezone

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.google_calendar.application.services.token_manager import (  # noqa: E402
    ensure_valid_access_token,
)
from app.google_calendar.infrastructure.api.google_calendar_client import (  # noqa: E402
    GoogleCalendarApiClient,
)
from app.google_calendar.infrastructure.persistence.repositories.calendar_connection_repo import (  # noqa: E402
    GoogleCalendarConnectionRepository,
)
from app.shared.infrastructure.config.settings import get_settings  # noqa: E402
from app.todo.infrastructure.persistence.repositories.todo_repo import (  # noqa: E402
    TodoRepository,
)

_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"

_BASES_SQL = """
SELECT id, user_id, title, date_key, recurrence_rule->>'until' AS until, google_event_id
FROM todos
WHERE recurrence_rule IS NOT NULL
  AND series_id IS NULL
  AND google_event_id IS NOT NULL
  AND calendar_push_status IS NOT NULL
  AND push_intent IS DISTINCT FROM 'delete'
ORDER BY created_at
"""


def _google_until(recurrence: list[str] | None) -> str | None:
    """Google RRULE 의 UNTIL 을 YYYYMMDD 로 정규화해 반환 (없으면 None = 무한 반복).

    Google 은 시간 이벤트에 datetime 형식(YYYYMMDDTHHMMSSZ)을 돌려줄 수 있어 날짜
    부분만 쓴다 — ARCHIVE 의 until 은 날짜(YYYY-MM-DD)라 그대로 비교하면 항상 불일치다.
    """
    for rule in recurrence or []:
        if "UNTIL=" in rule:
            return rule.split("UNTIL=")[1].split(";")[0][:8]
    return None


def _with_until(rrule: str, until_compact: str) -> str:
    """RRULE 의 UNTIL 을 치환(없으면 추가)."""
    parts = [p for p in rrule.split(";") if not p.startswith("UNTIL=")]
    return ";".join(parts) + f";UNTIL={until_compact}"


def _classify(row, event: dict | None, today: date) -> tuple[str, str]:
    """(action, 사유) — event 가 None/cancelled 면 Google 에 남은 게 없다."""
    if event is None:
        return "ok", "Google 에 이벤트 없음"
    if event.get("status") == "cancelled":
        return "ok", "Google 에서 이미 삭제됨"
    archive_until = row.until
    g_until = _google_until(event.get("recurrence"))
    if archive_until and archive_until < row.date_key:
        start = (event.get("start") or {}).get("dateTime") or (event.get("start") or {}).get("date")
        starts_in_future = start is not None and start[:10] > today.isoformat()
        if g_until is not None and g_until <= today.isoformat().replace("-", ""):
            return "ok", "이미 종료됨"
        return ("delete", "빈 시리즈 + 과거 회차 없음") if starts_in_future else (
            "stop-future",
            "빈 시리즈 + 과거 회차 보존",
        )
    expected = archive_until.replace("-", "") if archive_until else None
    if (g_until or None) == expected:
        return "ok", "일치"
    detail = f"Google UNTIL={g_until or '없음'} → {expected or '없음'}"
    # 어느 한쪽이라도 오늘 이후까지 걸쳐 있으면 미래 회차에 영향이 있다.
    today_compact = today.isoformat().replace("-", "")
    has_future = (g_until is None or g_until > today_compact) or (
        expected is None or expected > today_compact
    )
    return ("repush", detail) if has_future else ("repush-past", detail + " (과거 구간만)")


async def _fetch_event(client: httpx.AsyncClient, token: str, gid: str) -> dict | None:
    r = await client.get(f"{_EVENTS_URL}/{gid}", headers={"Authorization": f"Bearer {token}"})
    if r.status_code in (404, 410):
        return None
    r.raise_for_status()
    return r.json()


async def _patch_until(
    client: httpx.AsyncClient, token: str, gid: str, recurrence: list[str], until_compact: str
) -> None:
    """RRULE 에만 UNTIL 을 넣고 나머지 항목(EXDATE 등)은 그대로 보존해 PATCH."""
    patched = [
        _with_until(r, until_compact) if r.startswith("RRULE") else r for r in recurrence
    ]
    r = await client.patch(
        f"{_EVENTS_URL}/{gid}",
        headers={"Authorization": f"Bearer {token}"},
        json={"recurrence": patched},
    )
    r.raise_for_status()


async def _delete_event(client: httpx.AsyncClient, token: str, gid: str) -> None:
    r = await client.delete(f"{_EVENTS_URL}/{gid}", headers={"Authorization": f"Bearer {token}"})
    if r.status_code not in (200, 204, 404, 410):
        r.raise_for_status()


async def run(db_url: str, apply: bool, include_past: bool) -> int:
    settings = get_settings()
    engine = create_async_engine(db_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    api_client = GoogleCalendarApiClient(settings.google_calendar)
    today = datetime.now(timezone.utc).date()
    yesterday_compact = (today - timedelta(days=1)).isoformat().replace("-", "")
    changed = 0
    try:
        async with factory.begin() as session:
            rows = (await session.execute(text(_BASES_SQL))).all()
        if not rows:
            print("연동된 반복 시리즈가 없습니다.")
            return 0

        tokens: dict[str, str] = {}
        for user_id in {r.user_id for r in rows}:
            async with factory.begin() as session:
                conn_repo = GoogleCalendarConnectionRepository(session)
                conn = await conn_repo.find_by_user_id(user_id)
                token = (
                    await ensure_valid_access_token(
                        conn, api_client, conn_repo, datetime.now(timezone.utc)
                    )
                    if conn
                    else None
                )
            if token is None:
                print(f"[skip] {user_id}: 캘린더 미연결이거나 재인증 필요")
                continue
            tokens[user_id] = token

        async with httpx.AsyncClient(timeout=20) as client:
            for row in rows:
                token = tokens.get(row.user_id)
                if token is None:
                    continue
                event = await _fetch_event(client, token, row.google_event_id)
                action, reason = _classify(row, event, today)
                print(
                    f"{action:<12} {row.title[:16]:<18} start={row.date_key} "
                    f"until={row.until or '없음':<11} {reason}"
                )
                if action == "repush-past" and not include_past:
                    continue
                if action == "ok" or not apply:
                    continue

                if action in ("repush", "repush-past"):
                    async with factory.begin() as session:
                        await TodoRepository(session).mark_for_push(row.id, row.user_id)
                elif action == "stop-future":
                    await _patch_until(
                        client,
                        token,
                        row.google_event_id,
                        (event or {}).get("recurrence", []),
                        yesterday_compact,
                    )
                    async with factory.begin() as session:
                        await TodoRepository(session).clear_calendar_link(row.id, row.user_id)
                elif action == "delete":
                    await _delete_event(client, token, row.google_event_id)
                    async with factory.begin() as session:
                        await TodoRepository(session).clear_calendar_link(row.id, row.user_id)
                changed += 1
    finally:
        await api_client.close()
        await engine.dispose()

    if apply:
        print(
            f"\n{changed}건 반영. repush 대상은 캘린더 워커 배치(최대 5분)가 Google 에 갱신합니다."
        )
    else:
        print("\n[dry-run] --apply 를 붙이면 위 조치를 실제로 반영합니다.")
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--apply", action="store_true", help="실제 반영 (Google 쓰기 포함)")
    parser.add_argument(
        "--include-past",
        action="store_true",
        help="과거 구간만 다른 시리즈도 맞춘다 (Google 의 과거 일정이 지워질 수 있음)",
    )
    args = parser.parse_args()
    if not args.db_url:
        parser.error("DATABASE_URL 환경변수 또는 --db-url 이 필요합니다.")
    asyncio.run(run(args.db_url, args.apply, args.include_past))


if __name__ == "__main__":
    main()
