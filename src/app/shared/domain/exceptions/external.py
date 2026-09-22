"""여러 모듈이 공유하는 외부 연동(메일·캐시·AI) 실패 예외.

외부 라이브러리 예외(aiosmtplib, redis, google-genai, httpx)는 infrastructure 경계에서
이 예외들로 번역된다 — 상위 레이어는 라이브러리를 몰라도 실패 종류별로 대응할 수 있다.
"""
from app.shared.domain.exceptions.base import BaseAppException


class EmailDeliveryFailedException(BaseAppException):
    """SMTP 발송 실패 (연결·인증·수신 거부·타임아웃)."""
    code = "EMAIL_DELIVERY_FAILED"


class CacheUnavailableException(BaseAppException):
    """Redis 연결·타임아웃 등 캐시 계층 장애. 보안 기능(로그인 제한 등)은 fail-closed."""
    code = "CACHE_UNAVAILABLE"


# ── AI (Gemini) ────────────────────────────────────────────────────────────────
# 워커(요약·다이제스트·임베딩)에서 주로 발생한다. 대응이 서로 다르다:
#   Unavailable/QuotaExceeded → 재시도,  RequestRejected/EmptyResponse → 재시도 무의미.

class AIServiceException(BaseAppException):
    """AI 호출 실패 공통 부모 — '어떤 AI 실패든 degrade' 하는 경로에서만 이걸 잡는다."""
    code = "AI_SERVICE_ERROR"


class AIServiceUnavailableException(AIServiceException):
    """일시 장애 (5xx·네트워크·타임아웃). 재시도 대상."""
    code = "AI_SERVICE_UNAVAILABLE"


class AIQuotaExceededException(AIServiceUnavailableException):
    """429 쿼터/속도 제한. 일시 장애의 일종이지만 더 긴 백오프가 필요하다."""
    code = "AI_QUOTA_EXCEEDED"


class AIRequestRejectedException(AIServiceException):
    """4xx — API 키·권한·요청 형식(길이 초과 등) 문제. 재시도해도 같다 → 설정/코드 확인."""
    code = "AI_REQUEST_REJECTED"


class AIEmptyResponseException(AIServiceException):
    """응답에 결과가 없음 (safety filter·빈 candidates·빈 임베딩)."""
    code = "AI_EMPTY_RESPONSE"
