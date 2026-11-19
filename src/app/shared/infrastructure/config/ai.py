from pydantic_settings import BaseSettings, SettingsConfigDict


class AIConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    google_api_key: str
    gemini_model: str = "gemini-2.5-flash"
    # Gemini 호출 클라이언트 타임아웃(밀리초). 응답이 이 시간 내 안 오면 무한 대기
    # 대신 TimeoutException 발생 → 워커가 hang 된 호출에 묶이는 것을 방지. env: GEMINI_TIMEOUT_MS
    gemini_timeout_ms: int = 60000
    # AI 비서(대화·제안) 사용자별 요청 상한 — 사용자 tz 하루/한 달. 규칙 기반 추천은 세지 않는다.
    ai_daily_request_limit: int = 50
    ai_monthly_request_limit: int = 1000
