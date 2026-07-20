"""국가 변경 이력 엔티티 — 통계/분석용 audit log."""
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class CountryChangeSource(StrEnum):
    REGISTRATION = "registration"           # 이메일 회원가입
    OAUTH_ONBOARDING = "oauth_onboarding"   # OAuth 신규 가입 온보딩
    SETTINGS_UPDATE = "settings_update"     # Settings 에서 사용자 직접 변경


@dataclass
class CountryChangeRecord:
    id: str
    user_id: str
    country: str            # ISO 3166-1 alpha-2
    region: str | None      # ISO 3166-2 (다중 tz 국가만)
    timezone: str           # IANA tz
    source: CountryChangeSource
    created_at: datetime
