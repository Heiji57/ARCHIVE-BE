from pydantic_settings import BaseSettings, SettingsConfigDict


class RetrospectiveConfig(BaseSettings):
    """회고 도메인 운영 파라미터.

    환경변수 prefix 없음 — 일반 env 키로 노출.
    - SUMMARY_TEMPLATE_MAX_PER_TYPE : 사용자 1명이 한 summary_type 안에 만들 수 있는
      템플릿 최대 개수 (기본 5)
    """
    model_config = SettingsConfigDict(env_file=".env.local", extra="ignore")

    summary_template_max_per_type: int = 5
