from datetime import datetime

import structlog

from app.google_calendar.domain.exceptions.exceptions import (
    CalendarReauthRequiredException,
)
from app.google_calendar.domain.models.calendar_connection import GoogleCalendarConnection
from app.google_calendar.domain.repositories.repository import (
    IGoogleCalendarConnectionRepository,
)
from app.google_calendar.infrastructure.api.google_calendar_client import (
    GoogleCalendarApiClient,
)

_log = structlog.get_logger(__name__)


async def ensure_valid_access_token(
    conn: GoogleCalendarConnection,
    api_client: GoogleCalendarApiClient,
    connection_repo: IGoogleCalendarConnectionRepository,
    now: datetime,
) -> str | None:
    """유효한 access_token 을 확보한다 (pull-sync / push 공용).

    - needs_reauth → None (호출자는 해당 사이클 스킵).
    - 미만료 → 현재 access_token.
    - 만료 → refresh_token 으로 갱신 후 conn 갱신·즉시 persist(갱신 토큰 유실 방지),
      새 access_token 반환.
    - refresh 실패(invalid_grant 등) → needs_reauth 마킹·persist 후 None.

    refresh 실패 시 needs_reauth 저장까지 이 헬퍼가 책임진다 — 호출자마다 저장을
    잊는 실수를 구조적으로 차단(반복 refresh 방지).
    """
    if conn.needs_reauth:
        return None
    if not conn.is_token_expired(now):
        return conn.access_token

    try:
        tokens = await api_client.refresh_access_token(conn.refresh_token)
    except CalendarReauthRequiredException:
        _log.warning("calendar.token.reauth_required", user_id=conn.user_id)
        conn.needs_reauth = True
        conn.updated_at = now
        await connection_repo.save(conn)
        return None

    conn.apply_refreshed_token(tokens.access_token, tokens.expires_in, now)
    if tokens.refresh_token:
        conn.refresh_token = tokens.refresh_token
    await connection_repo.save(conn)
    return conn.access_token
