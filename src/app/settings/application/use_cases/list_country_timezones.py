"""국가별 IANA timezone 옵션 조회.

FE 가 국가 선택 시 호출 → 단일 tz 국가면 1개, 다중 tz 국가면 여러 개 옵션 반환.
"""
from dataclasses import dataclass

from app.auth.domain.exceptions.exceptions import CountryInvalidException
from app.shared.domain.utils.timezone import (
    country_timezone_options,
    is_supported_country,
)


@dataclass(frozen=True)
class CountryTimezoneListResult:
    country: str
    timezones: list[str]
    multi: bool


class ListCountryTimezonesUseCase:
    async def execute(self, country: str) -> CountryTimezoneListResult:
        code = country.strip().upper()
        if not is_supported_country(code):
            raise CountryInvalidException(f"Unsupported country: {code}")
        options = country_timezone_options(code)
        if not options:
            # 이론상 일부 신생 국가는 pytz 데이터 누락 가능 — 명확히 404 적 도메인 에러
            raise CountryInvalidException(f"No timezone data for country: {code}")
        return CountryTimezoneListResult(
            country=code,
            timezones=options,
            multi=len(options) > 1,
        )
