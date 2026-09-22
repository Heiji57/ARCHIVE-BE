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


# 아래 둘은 CalendarApiUnavailableException 의 하위 — 기존 "API 호출 실패" 처리(sync skip,
# push 실패 확정)를 그대로 타되, 코드/상태와 대응(속도 제한은 실패 카운트 제외)을 구분한다.

class CalendarRateLimitedException(CalendarApiUnavailableException):
    """429 또는 403 rateLimitExceeded/userRateLimitExceeded — 잠시 후 재시도."""
    code = "GOOGLE_CALENDAR_RATE_LIMITED"


class CalendarResponseInvalidException(CalendarApiUnavailableException):
    """Google 응답이 예상 형식이 아님 (비JSON·필수 필드 누락)."""
    code = "GOOGLE_CALENDAR_RESPONSE_INVALID"
