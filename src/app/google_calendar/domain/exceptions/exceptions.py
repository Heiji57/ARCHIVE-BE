from app.shared.domain.exceptions.base import BaseAppException


class CalendarNotConnectedException(BaseAppException):
    """사용자가 Google Calendar 를 아직 연결하지 않음."""
    code = "GOOGLE_CALENDAR_NOT_CONNECTED"


class CalendarReauthRequiredException(BaseAppException):
    """refresh_token 이 무효(만료/revoke) — 사용자가 재연결해야 함."""
    code = "GOOGLE_CALENDAR_REAUTH_REQUIRED"


class CalendarStateInvalidException(BaseAppException):
    """OAuth state 가 무효하거나 만료됨 (CSRF 방어)."""
    code = "GOOGLE_CALENDAR_STATE_INVALID"


class CalendarApiUnavailableException(BaseAppException):
    """Google Calendar API 호출 실패 (5xx / 네트워크)."""
    code = "GOOGLE_CALENDAR_API_UNAVAILABLE"
