"""국가 ↔ IANA 타임존 매핑.

데이터 소스:
- pycountry: ISO 3166-1 alpha-2 (249개국) 정식 목록
- pytz.country_timezones: CLDR-derived 국가 → IANA tz 목록

원칙:
- 국가의 tz 가 1개 = "단일 tz 국가" → country 만으로 결정
- 국가의 tz 가 2개 이상 = "다중 tz 국가" → timezone 파라미터 필수,
  해당 timezone 이 그 국가의 옵션에 속해야 함

이 모듈은 timezone 데이터를 직접 보관하지 않는다. tzdata (system zoneinfo) 와
pytz 가 권위 데이터 — OS / 라이브러리 업데이트 시 자동 추적된다.
"""
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pycountry
import pytz

# ISO 3166-1 alpha-2 모든 코드 (249개)
_SUPPORTED_COUNTRY_CODES: frozenset[str] = frozenset(
    c.alpha_2 for c in pycountry.countries
)


def is_supported_country(country: str) -> bool:
    """ISO 3166-1 alpha-2 등록된 국가 코드인지."""
    return country.upper() in _SUPPORTED_COUNTRY_CODES


def country_timezone_options(country: str) -> list[str]:
    """국가에 속한 IANA tz 옵션 목록.

    빈 리스트면 tz 데이터 없음 (이론상 South Sudan(SS) 등 일부 누락 케이스).
    1개면 단일 tz 국가, 2개 이상이면 다중 tz 국가.
    """
    return list(pytz.country_timezones.get(country.upper(), []))


def is_multi_tz_country(country: str) -> bool:
    """다중 tz 국가 여부 (tz 옵션이 2개 이상)."""
    return len(country_timezone_options(country)) > 1


def resolve_timezone(country: str, timezone: str | None = None) -> str:
    """국가 + (옵션 timezone) 조합으로 IANA tz 문자열 결정.

    단일 tz 국가: timezone 없어도 자동 결정. 주어졌다면 옵션에 속해야 함.
    다중 tz 국가: timezone 필수. 해당 국가의 옵션에 속해야 함.

    Raises:
        ValueError: 지원하지 않는 country, tz 데이터 없는 country,
                    다중 tz 국가에서 timezone 누락, 또는 timezone 이 country 옵션 밖.
    """
    country_code = country.upper()
    if not is_supported_country(country_code):
        raise ValueError(f"Unsupported country code: {country_code}")

    options = country_timezone_options(country_code)
    if not options:
        raise ValueError(f"No timezone data for country: {country_code}")

    if len(options) == 1:
        sole = options[0]
        if timezone and timezone != sole:
            raise ValueError(
                f"Timezone '{timezone}' does not belong to country '{country_code}' "
                f"(only option: {sole})"
            )
        return sole

    # 다중 tz 국가
    if not timezone:
        raise ValueError(
            f"Multi-timezone country '{country_code}' requires explicit timezone "
            f"(options: {options})"
        )
    if timezone not in options:
        raise ValueError(
            f"Timezone '{timezone}' does not belong to country '{country_code}'"
        )
    return timezone


def validate_timezone(tz: str) -> bool:
    """IANA tz 문자열 유효성 검증 (zoneinfo 로 로드 가능한지)."""
    try:
        ZoneInfo(tz)
        return True
    except ZoneInfoNotFoundError:
        return False
