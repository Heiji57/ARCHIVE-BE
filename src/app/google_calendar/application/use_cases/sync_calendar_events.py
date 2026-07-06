from datetime import datetime, timedelta, timezone

import structlog

from app.google_calendar.domain.exceptions.exceptions import (
    CalendarApiUnavailableException,
    CalendarReauthRequiredException,
)
from app.google_calendar.domain.models.calendar_connection import GoogleCalendarConnection
from app.google_calendar.domain.models.calendar_event import CalendarEvent
from app.google_calendar.application.services.token_manager import (
    ensure_valid_access_token,
)
from app.google_calendar.domain.repositories.repository import (
    ICalendarEventRepository,
    IGoogleCalendarConnectionRepository,
)
from app.google_calendar.infrastructure.api.google_calendar_client import (
    CalendarEventsPage,
    CalendarSyncTokenExpiredError,
    GoogleCalendarApiClient,
    RawCalendarEvent,
)
from app.shared.domain.utils.id import generate_id
from app.shared.infrastructure.config.oauth import GoogleCalendarConfig

_log = structlog.get_logger(__name__)


class SyncCalendarEventsUseCase:
    """사용자 캘린더 이벤트를 Google 과 동기화 (증분 우선).

    - 미연결 → None.
    - needs_reauth → 토큰 무효 상태이므로 sync 스킵하고 connection 그대로 반환 (FE 재연결 유도).
    - last_synced_at 이 staleness 이내면 스킵 (force=True 면 무시).
    - access_token 만료 시 refresh_token 으로 갱신. 갱신 실패 → needs_reauth 마킹.
    - syncToken 만료(410) → full resync (기존 이벤트 삭제 후 윈도우 재조회).
    - Google API 일시 장애 → 저장된 이벤트 유지하고 조용히 반환 (연결 보존).
    """

    def __init__(
        self,
        connection_repo: IGoogleCalendarConnectionRepository,
        event_repo: ICalendarEventRepository,
        api_client: GoogleCalendarApiClient,
        config: GoogleCalendarConfig,
    ) -> None:
        self._connection_repo = connection_repo
        self._event_repo = event_repo
        self._api_client = api_client
        self._config = config

    async def execute(
        self, user_id: str, force: bool = False
    ) -> GoogleCalendarConnection | None:
        conn = await self._connection_repo.find_by_user_id(user_id)
        if conn is None:
            return None
        if conn.needs_reauth:
            return conn

        now = datetime.now(timezone.utc)

        if not force and conn.last_synced_at is not None:
            age = (now - conn.last_synced_at).total_seconds()
            if age < self._config.calendar_sync_staleness_seconds:
                return conn

        # ── 토큰 갱신 (pull-sync / push 공용 헬퍼) ──────────────────────────────
        access_token = await ensure_valid_access_token(
            conn, self._api_client, self._connection_repo, now
        )
        if access_token is None:
            return conn  # needs_reauth — FE 재연결 유도

        # ── 이벤트 조회 (증분 / full) ──────────────────────────────────────────
        try:
            page = await self._fetch(conn, now)
        except CalendarSyncTokenExpiredError:
            _log.info("calendar.sync.token_expired_full_resync", user_id=user_id)
            conn.sync_token = None
            await self._event_repo.delete_all_by_user(user_id)
            try:
                page = await self._fetch(conn, now)
            except CalendarApiUnavailableException:
                return conn
        except CalendarReauthRequiredException:
            conn.needs_reauth = True
            conn.updated_at = now
            await self._connection_repo.save(conn)
            return conn
        except CalendarApiUnavailableException:
            _log.warning("calendar.sync.api_unavailable", user_id=user_id)
            return conn

        # ── upsert + cancelled 삭제 ────────────────────────────────────────────
        to_upsert: list[CalendarEvent] = []
        cancelled_ids: list[str] = []
        for raw in page.events:
            if raw.status == "cancelled":
                cancelled_ids.append(raw.google_event_id)
            elif raw.archive_todo_id is not None:
                # ARCHIVE 가 push 한 이벤트 — read-model 에 mirror 하지 않는다(순환 방지).
                # todo 자체가 원본이므로 calendar_events 로 되돌려 받을 필요 없음.
                continue
            else:
                to_upsert.append(self._to_entity(raw, conn, now))

        await self._event_repo.delete_by_google_ids(user_id, cancelled_ids)
        await self._event_repo.upsert_many(to_upsert)

        conn.sync_token = page.next_sync_token or conn.sync_token
        conn.last_synced_at = now
        conn.updated_at = now
        await self._connection_repo.save(conn)
        return conn

    async def _fetch(
        self, conn: GoogleCalendarConnection, now: datetime
    ) -> CalendarEventsPage:
        if conn.sync_token:
            return await self._api_client.list_events(
                conn.access_token, sync_token=conn.sync_token
            )
        time_min = (
            now - timedelta(days=self._config.calendar_initial_window_days)
        ).isoformat()
        time_max = (
            now + timedelta(days=self._config.calendar_future_window_days)
        ).isoformat()
        return await self._api_client.list_events(
            conn.access_token, time_min=time_min, time_max=time_max
        )

    def _to_entity(
        self, raw: RawCalendarEvent, conn: GoogleCalendarConnection, now: datetime
    ) -> CalendarEvent:
        return CalendarEvent(
            id=generate_id("cevt"),
            user_id=conn.user_id,
            connection_id=conn.id,
            google_event_id=raw.google_event_id,
            calendar_id=raw.calendar_id,
            title=raw.title,
            description=raw.description,
            location=raw.location,
            start_at=raw.start_at,
            end_at=raw.end_at,
            all_day=raw.all_day,
            date_key=raw.date_key,
            timezone=raw.timezone,
            status=raw.status,
            html_link=raw.html_link,
            created_at=now,
            updated_at=now,
        )
