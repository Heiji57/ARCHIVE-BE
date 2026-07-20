"""Google Calendar API + OAuth 토큰 클라이언트.

단일 long-lived httpx.AsyncClient 재사용 (커넥션 풀링) — APP scope 로 dishka 등록,
lifespan 종료 시 `close()`.

설계:
- OAuth 토큰 교환/갱신과 Calendar v3 events.list 를 한 곳에서 처리.
- 증분 동기화(`syncToken`) 우선. syncToken 만료(410 GONE) 시 `CalendarSyncTokenExpiredError`
  를 던져 use case 가 full resync 하도록 한다.
- refresh_token 이 무효(`invalid_grant`) 면 `CalendarReauthRequiredException` 으로 변환 —
  use case 가 connection.needs_reauth 로 마킹하고 FE 가 재연결 유도.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from urllib.parse import urlencode

import httpx

from app.google_calendar.domain.exceptions.exceptions import (
    CalendarApiUnavailableException,
    CalendarReauthRequiredException,
)
from app.shared.infrastructure.config.oauth import GoogleCalendarConfig

_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
_CALENDAR_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"
_PRIMARY_CALENDAR = "primary"
_PAGE_SIZE = 2500
_MAX_PAGES = 20

_DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0)


class CalendarSyncTokenExpiredError(Exception):
    """syncToken 이 만료/무효(410 GONE) — full resync 필요. use case 내부 신호."""


@dataclass(frozen=True)
class CalendarTokenBundle:
    access_token: str
    refresh_token: str | None
    expires_in: int


@dataclass(frozen=True)
class RawCalendarEvent:
    google_event_id: str
    calendar_id: str
    title: str
    description: str | None
    location: str | None
    start_at: datetime | None
    end_at: datetime | None
    all_day: bool
    date_key: str
    timezone: str | None
    status: str
    html_link: str | None
    # ARCHIVE 가 push 한 이벤트면 extendedProperties.private.archiveTodoId 값(원본 todo id).
    # None 이면 사용자가 Google 에서 직접 만든 이벤트 → pull-sync 에서 그대로 mirror.
    archive_todo_id: str | None = None


# 사용자 소유 tag key — ARCHIVE push 이벤트 식별 및 순환 동기화 차단에 사용.
ARCHIVE_TODO_ID_KEY = "archiveTodoId"


@dataclass(frozen=True)
class CalendarEventWrite:
    """Todo → Google Calendar 이벤트 쓰기 입력(도메인 비의존 중립 구조).

    start_at 이 None 이면 date_key 종일(all-day) 이벤트, non-null 이면 시간 이벤트.
    시간은 UTC datetime 으로 전달하고 timezone(IANA snapshot)은 표시용으로 함께 보낸다.
    """
    archive_todo_id: str
    title: str
    description: str | None
    date_key: str
    start_at: datetime | None
    end_at: datetime | None
    timezone: str | None


@dataclass(frozen=True)
class CalendarEventsPage:
    events: list[RawCalendarEvent]
    next_sync_token: str | None


def _parse_event(item: dict, calendar_id: str) -> RawCalendarEvent | None:
    """Google events.list item → RawCalendarEvent.

    cancelled 이벤트는 id/status 만 있을 수 있어 그대로 통과시킨다(use case 가 삭제 처리).
    date_key 없는 비정상 항목은 None 반환(스킵).
    """
    status = item.get("status", "confirmed")
    event_id = item.get("id")
    if not event_id:
        return None

    start = item.get("start") or {}
    end = item.get("end") or {}

    # cancelled 이벤트는 start/end 가 없을 수 있음 — 삭제 처리용 최소 정보만.
    if status == "cancelled" and not start:
        return RawCalendarEvent(
            google_event_id=event_id,
            calendar_id=calendar_id,
            title=item.get("summary") or "",
            description=None,
            location=None,
            start_at=None,
            end_at=None,
            all_day=False,
            date_key="",
            timezone=None,
            status="cancelled",
            html_link=None,
        )

    all_day = "date" in start
    start_at: datetime | None = None
    end_at: datetime | None = None
    timezone: str | None = None

    if all_day:
        date_key = start.get("date", "")
    else:
        start_dt_raw = start.get("dateTime")
        if not start_dt_raw:
            return None
        start_at = datetime.fromisoformat(start_dt_raw)
        date_key = start_at.date().isoformat()
        timezone = start.get("timeZone")
        end_dt_raw = end.get("dateTime")
        if end_dt_raw:
            end_at = datetime.fromisoformat(end_dt_raw)

    if not date_key:
        return None

    private_props = (item.get("extendedProperties") or {}).get("private") or {}
    archive_todo_id = private_props.get(ARCHIVE_TODO_ID_KEY)

    return RawCalendarEvent(
        google_event_id=event_id,
        calendar_id=calendar_id,
        title=item.get("summary") or "(No title)",
        description=item.get("description"),
        location=item.get("location"),
        start_at=start_at,
        end_at=end_at,
        all_day=all_day,
        date_key=date_key,
        timezone=timezone,
        status=status,
        html_link=item.get("htmlLink"),
        archive_todo_id=archive_todo_id,
    )


class GoogleCalendarApiClient:
    def __init__(self, config: GoogleCalendarConfig) -> None:
        self._config = config
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def close(self) -> None:
        await self._client.aclose()

    @property
    def scope(self) -> str:
        return self._config.calendar_scope

    # ── OAuth ────────────────────────────────────────────────────────────────

    def build_authorize_url(self, state: str) -> str:
        params = urlencode({
            "client_id": self._config.client_id,
            "redirect_uri": self._config.calendar_redirect_uri,
            "response_type": "code",
            "scope": self._config.calendar_scope,
            "state": state,
            # refresh_token 확보를 위해 offline + 매번 동의(consent) 강제.
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
        })
        return f"{_AUTH_URL}?{params}"

    async def exchange_code(self, code: str) -> CalendarTokenBundle:
        response = await self._client.post(
            _TOKEN_URL,
            data={
                "client_id": self._config.client_id,
                "client_secret": self._config.client_secret,
                "code": code,
                "redirect_uri": self._config.calendar_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if response.status_code >= 400:
            raise CalendarReauthRequiredException(
                f"Token exchange failed: {response.text[:200]}"
            )
        data = response.json()
        return CalendarTokenBundle(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_in=int(data.get("expires_in", 3600)),
        )

    async def refresh_access_token(self, refresh_token: str) -> CalendarTokenBundle:
        response = await self._client.post(
            _TOKEN_URL,
            data={
                "client_id": self._config.client_id,
                "client_secret": self._config.client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        if response.status_code >= 400:
            # invalid_grant 등 → refresh_token 무효, 사용자 재연결 필요.
            raise CalendarReauthRequiredException(
                f"Token refresh failed: {response.text[:200]}"
            )
        data = response.json()
        return CalendarTokenBundle(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_in=int(data.get("expires_in", 3600)),
        )

    async def get_user_id(self, access_token: str) -> str:
        response = await self._client.get(
            _USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if response.status_code >= 400:
            raise CalendarReauthRequiredException("Failed to fetch Google user info.")
        return response.json()["id"]

    # ── Calendar ───────────────────────────────────────────────────────────────

    async def list_events(
        self,
        access_token: str,
        *,
        time_min: str | None = None,
        time_max: str | None = None,
        sync_token: str | None = None,
        calendar_id: str = _PRIMARY_CALENDAR,
    ) -> CalendarEventsPage:
        """primary 캘린더 이벤트 조회. sync_token 있으면 증분, 없으면 [time_min, time_max] 전체.

        모든 페이지를 순회해 누적하고 마지막 응답의 nextSyncToken 을 반환한다.
        410 GONE(syncToken 만료) → CalendarSyncTokenExpiredError.
        """
        events: list[RawCalendarEvent] = []
        page_token: str | None = None
        next_sync_token: str | None = None
        url = _CALENDAR_EVENTS_URL.format(calendar_id=calendar_id)

        for _ in range(_MAX_PAGES):
            params: dict[str, str | int] = {"maxResults": _PAGE_SIZE}
            if sync_token:
                params["syncToken"] = sync_token
            else:
                params["singleEvents"] = "true"
                params["showDeleted"] = "false"
                if time_min:
                    params["timeMin"] = time_min
                if time_max:
                    params["timeMax"] = time_max
            if page_token:
                params["pageToken"] = page_token

            response = await self._client.get(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
            )

            if response.status_code == 410:
                raise CalendarSyncTokenExpiredError()
            if response.status_code == 401:
                raise CalendarReauthRequiredException("Calendar API returned 401.")
            if response.status_code >= 400:
                raise CalendarApiUnavailableException(
                    f"Calendar API returned {response.status_code}: {response.text[:200]}"
                )

            data = response.json()
            for item in data.get("items", []):
                parsed = _parse_event(item, calendar_id)
                if parsed is not None:
                    events.append(parsed)

            next_sync_token = data.get("nextSyncToken") or next_sync_token
            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return CalendarEventsPage(events=events, next_sync_token=next_sync_token)

    # ── Calendar write (ARCHIVE todo → Google) ───────────────────────────────────

    def _build_event_body(self, ev: CalendarEventWrite) -> dict:
        """CalendarEventWrite → Google events insert/update body.

        - archiveTodoId 를 extendedProperties.private 에 심어 ARCHIVE 소유임을 표시
          (순환 동기화 차단 + 404 시 재조회 키).
        - start_at 없음 → 종일 이벤트(end.date 는 exclusive 이므로 date_key + 1일).
        - start_at 있음 → 시간 이벤트(end 미지정 시 start + 1h). UTC dateTime + IANA tz.
        """
        body: dict = {
            "summary": ev.title,
            "description": ev.description or "",
            "extendedProperties": {"private": {ARCHIVE_TODO_ID_KEY: ev.archive_todo_id}},
        }
        if ev.start_at is None:
            end_date = (date.fromisoformat(ev.date_key) + timedelta(days=1)).isoformat()
            body["start"] = {"date": ev.date_key}
            body["end"] = {"date": end_date}
        else:
            tz = ev.timezone or "UTC"
            end_at = ev.end_at or (ev.start_at + timedelta(hours=1))
            body["start"] = {"dateTime": ev.start_at.isoformat(), "timeZone": tz}
            body["end"] = {"dateTime": end_at.isoformat(), "timeZone": tz}
        return body

    async def create_event(
        self,
        access_token: str,
        ev: CalendarEventWrite,
        calendar_id: str = _PRIMARY_CALENDAR,
    ) -> str:
        """이벤트 생성 후 Google event id 반환."""
        url = _CALENDAR_EVENTS_URL.format(calendar_id=calendar_id)
        response = await self._client.post(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            json=self._build_event_body(ev),
        )
        if response.status_code == 401:
            raise CalendarReauthRequiredException("Calendar API returned 401 on create.")
        if response.status_code >= 400:
            raise CalendarApiUnavailableException(
                f"Calendar create failed {response.status_code}: {response.text[:200]}"
            )
        return response.json()["id"]

    async def update_event(
        self,
        access_token: str,
        google_event_id: str,
        ev: CalendarEventWrite,
        calendar_id: str = _PRIMARY_CALENDAR,
    ) -> str | None:
        """이벤트 갱신 후 id 반환. 404(이벤트 사라짐)면 None → 호출자가 create fallback."""
        base = _CALENDAR_EVENTS_URL.format(calendar_id=calendar_id)
        response = await self._client.put(
            f"{base}/{google_event_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            json=self._build_event_body(ev),
        )
        if response.status_code in (404, 410):
            return None
        if response.status_code == 401:
            raise CalendarReauthRequiredException("Calendar API returned 401 on update.")
        if response.status_code >= 400:
            raise CalendarApiUnavailableException(
                f"Calendar update failed {response.status_code}: {response.text[:200]}"
            )
        return response.json()["id"]

    async def delete_event(
        self,
        access_token: str,
        google_event_id: str,
        calendar_id: str = _PRIMARY_CALENDAR,
    ) -> None:
        """이벤트 삭제. 404/410(이미 삭제됨)은 멱등 성공으로 처리."""
        base = _CALENDAR_EVENTS_URL.format(calendar_id=calendar_id)
        response = await self._client.delete(
            f"{base}/{google_event_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if response.status_code in (200, 204, 404, 410):
            return
        if response.status_code == 401:
            raise CalendarReauthRequiredException("Calendar API returned 401 on delete.")
        raise CalendarApiUnavailableException(
            f"Calendar delete failed {response.status_code}: {response.text[:200]}"
        )

    async def find_event_id_by_archive_todo_id(
        self,
        access_token: str,
        archive_todo_id: str,
        calendar_id: str = _PRIMARY_CALENDAR,
    ) -> str | None:
        """archiveTodoId 태그로 기존 이벤트 조회(defensive) — create 직전 중복 방지.

        create 성공 후 finalize 전에 워커가 죽었을 때, 재시도가 같은 todo 로 중복
        이벤트를 만드는 크래시 윈도우를 닫는다. syncToken 없이 targeted list 호출.
        """
        url = _CALENDAR_EVENTS_URL.format(calendar_id=calendar_id)
        response = await self._client.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "privateExtendedProperty": f"{ARCHIVE_TODO_ID_KEY}={archive_todo_id}",
                "maxResults": 5,
                "showDeleted": "false",
                "singleEvents": "true",
            },
        )
        if response.status_code == 401:
            raise CalendarReauthRequiredException("Calendar API returned 401 on lookup.")
        if response.status_code >= 400:
            raise CalendarApiUnavailableException(
                f"Calendar lookup failed {response.status_code}: {response.text[:200]}"
            )
        for item in response.json().get("items", []):
            if item.get("status") != "cancelled" and item.get("id"):
                return item["id"]
        return None
