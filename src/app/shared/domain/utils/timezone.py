"""국가/하위지역 → IANA 타임존 매핑.

다중 tz 국가는 region(ISO 3166-2 subdivision code) 필수.
단일 tz 국가는 region 없이도 결정 가능.
"""
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# 다중 tz 국가 — region(ISO 3166-2) 필수
MULTI_TZ_COUNTRIES: frozenset[str] = frozenset({
    "US", "CA", "RU", "AU", "BR", "MX", "ID", "AR", "CL", "KZ", "MN",
})

# 단일 tz 국가의 기본 IANA 타임존
SINGLE_TZ_COUNTRY: dict[str, str] = {
    "KR": "Asia/Seoul",
    "JP": "Asia/Tokyo",
    "CN": "Asia/Shanghai",     # 정책상 단일
    "TW": "Asia/Taipei",
    "HK": "Asia/Hong_Kong",
    "SG": "Asia/Singapore",
    "MY": "Asia/Kuala_Lumpur",
    "TH": "Asia/Bangkok",
    "VN": "Asia/Ho_Chi_Minh",
    "PH": "Asia/Manila",
    "IN": "Asia/Kolkata",
    "AE": "Asia/Dubai",
    "SA": "Asia/Riyadh",
    "IL": "Asia/Jerusalem",
    "TR": "Europe/Istanbul",
    "GB": "Europe/London",
    "IE": "Europe/Dublin",
    "FR": "Europe/Paris",
    "DE": "Europe/Berlin",
    "ES": "Europe/Madrid",
    "IT": "Europe/Rome",
    "NL": "Europe/Amsterdam",
    "BE": "Europe/Brussels",
    "CH": "Europe/Zurich",
    "AT": "Europe/Vienna",
    "PL": "Europe/Warsaw",
    "SE": "Europe/Stockholm",
    "NO": "Europe/Oslo",
    "DK": "Europe/Copenhagen",
    "FI": "Europe/Helsinki",
    "PT": "Europe/Lisbon",
    "GR": "Europe/Athens",
    "CZ": "Europe/Prague",
    "RO": "Europe/Bucharest",
    "HU": "Europe/Budapest",
    "UA": "Europe/Kyiv",
    "ZA": "Africa/Johannesburg",
    "EG": "Africa/Cairo",
    "NG": "Africa/Lagos",
    "KE": "Africa/Nairobi",
    "MA": "Africa/Casablanca",
    "NZ": "Pacific/Auckland",
}

# 다중 tz 국가의 region(ISO 3166-2) → IANA 타임존
REGION_TZ: dict[str, str] = {
    # ── 미국 (US) ──
    "US-AL": "America/Chicago",        # Alabama
    "US-AK": "America/Anchorage",      # Alaska
    "US-AZ": "America/Phoenix",        # Arizona (no DST)
    "US-AR": "America/Chicago",        # Arkansas
    "US-CA": "America/Los_Angeles",    # California
    "US-CO": "America/Denver",         # Colorado
    "US-CT": "America/New_York",       # Connecticut
    "US-DE": "America/New_York",       # Delaware
    "US-FL": "America/New_York",       # Florida (대부분)
    "US-GA": "America/New_York",       # Georgia
    "US-HI": "Pacific/Honolulu",       # Hawaii
    "US-ID": "America/Boise",          # Idaho
    "US-IL": "America/Chicago",        # Illinois
    "US-IN": "America/Indiana/Indianapolis",  # Indiana
    "US-IA": "America/Chicago",        # Iowa
    "US-KS": "America/Chicago",        # Kansas
    "US-KY": "America/New_York",       # Kentucky (동부)
    "US-LA": "America/Chicago",        # Louisiana
    "US-ME": "America/New_York",       # Maine
    "US-MD": "America/New_York",       # Maryland
    "US-MA": "America/New_York",       # Massachusetts
    "US-MI": "America/Detroit",        # Michigan
    "US-MN": "America/Chicago",        # Minnesota
    "US-MS": "America/Chicago",        # Mississippi
    "US-MO": "America/Chicago",        # Missouri
    "US-MT": "America/Denver",         # Montana
    "US-NE": "America/Chicago",        # Nebraska
    "US-NV": "America/Los_Angeles",    # Nevada
    "US-NH": "America/New_York",       # New Hampshire
    "US-NJ": "America/New_York",       # New Jersey
    "US-NM": "America/Denver",         # New Mexico
    "US-NY": "America/New_York",       # New York
    "US-NC": "America/New_York",       # North Carolina
    "US-ND": "America/Chicago",        # North Dakota
    "US-OH": "America/New_York",       # Ohio
    "US-OK": "America/Chicago",        # Oklahoma
    "US-OR": "America/Los_Angeles",    # Oregon
    "US-PA": "America/New_York",       # Pennsylvania
    "US-RI": "America/New_York",       # Rhode Island
    "US-SC": "America/New_York",       # South Carolina
    "US-SD": "America/Chicago",        # South Dakota
    "US-TN": "America/Chicago",        # Tennessee
    "US-TX": "America/Chicago",        # Texas
    "US-UT": "America/Denver",         # Utah
    "US-VT": "America/New_York",       # Vermont
    "US-VA": "America/New_York",       # Virginia
    "US-WA": "America/Los_Angeles",    # Washington
    "US-WV": "America/New_York",       # West Virginia
    "US-WI": "America/Chicago",        # Wisconsin
    "US-WY": "America/Denver",         # Wyoming
    "US-DC": "America/New_York",       # District of Columbia
    # ── 캐나다 (CA) ──
    "CA-ON": "America/Toronto",
    "CA-QC": "America/Toronto",
    "CA-BC": "America/Vancouver",
    "CA-AB": "America/Edmonton",
    "CA-MB": "America/Winnipeg",
    "CA-SK": "America/Regina",
    "CA-NS": "America/Halifax",
    "CA-NB": "America/Moncton",
    "CA-NL": "America/St_Johns",
    "CA-PE": "America/Halifax",
    "CA-YT": "America/Whitehorse",
    "CA-NT": "America/Yellowknife",
    "CA-NU": "America/Iqaluit",
    # ── 호주 (AU) ──
    "AU-NSW": "Australia/Sydney",
    "AU-VIC": "Australia/Melbourne",
    "AU-QLD": "Australia/Brisbane",
    "AU-SA":  "Australia/Adelaide",
    "AU-WA":  "Australia/Perth",
    "AU-TAS": "Australia/Hobart",
    "AU-NT":  "Australia/Darwin",
    "AU-ACT": "Australia/Sydney",
    # ── 러시아 (RU) — 주요 ──
    "RU-MOW": "Europe/Moscow",
    "RU-SPE": "Europe/Moscow",
    "RU-NVS": "Asia/Novosibirsk",
    "RU-SVE": "Asia/Yekaterinburg",
    "RU-PRI": "Asia/Vladivostok",
    "RU-KAM": "Asia/Kamchatka",
    "RU-KDA": "Europe/Moscow",
    # ── 브라질 (BR) — 주요 ──
    "BR-SP": "America/Sao_Paulo",
    "BR-RJ": "America/Sao_Paulo",
    "BR-DF": "America/Sao_Paulo",
    "BR-AM": "America/Manaus",
    "BR-AC": "America/Rio_Branco",
    "BR-PA": "America/Belem",
    # ── 멕시코 (MX) ──
    "MX-CMX": "America/Mexico_City",
    "MX-JAL": "America/Mexico_City",
    "MX-BCN": "America/Tijuana",
    "MX-BCS": "America/Mazatlan",
    "MX-CHH": "America/Chihuahua",
    "MX-SON": "America/Hermosillo",
    "MX-ROO": "America/Cancun",
    # ── 인도네시아 (ID) ──
    "ID-JK": "Asia/Jakarta",
    "ID-BA": "Asia/Makassar",
    "ID-PA": "Asia/Jayapura",
    # ── 아르헨티나 (AR) — 대부분 동일 ──
    "AR-B": "America/Argentina/Buenos_Aires",
    "AR-C": "America/Argentina/Buenos_Aires",
    # ── 칠레 (CL) ──
    "CL-RM": "America/Santiago",
    "CL-VS": "America/Santiago",
    "CL-MA": "America/Punta_Arenas",
    # ── 카자흐스탄 (KZ) ──
    "KZ-ALA": "Asia/Almaty",
    "KZ-AKT": "Asia/Aqtobe",
    # ── 몽골 (MN) ──
    "MN-1":  "Asia/Ulaanbaatar",
    "MN-64": "Asia/Hovd",
}


def is_multi_tz_country(country: str) -> bool:
    return country.upper() in MULTI_TZ_COUNTRIES


def is_supported_country(country: str) -> bool:
    code = country.upper()
    return code in MULTI_TZ_COUNTRIES or code in SINGLE_TZ_COUNTRY


def resolve_timezone(country: str, region: str | None = None) -> str:
    """국가/region 조합으로 IANA tz 문자열 결정.

    Raises:
        ValueError: 지원하지 않는 country, 또는 다중 tz 국가에서 region 누락/오류
    """
    country_code = country.upper()

    if country_code in SINGLE_TZ_COUNTRY:
        return SINGLE_TZ_COUNTRY[country_code]

    if country_code in MULTI_TZ_COUNTRIES:
        if not region:
            raise ValueError(f"Region required for multi-timezone country: {country_code}")
        region_code = region.upper()
        if not region_code.startswith(f"{country_code}-"):
            raise ValueError(f"Region '{region_code}' does not match country '{country_code}'")
        if region_code not in REGION_TZ:
            raise ValueError(f"Unsupported region code: {region_code}")
        return REGION_TZ[region_code]

    raise ValueError(f"Unsupported country code: {country_code}")


def validate_timezone(tz: str) -> bool:
    """IANA tz 문자열 유효성 검증 (zoneinfo로 로드 가능한지)."""
    try:
        ZoneInfo(tz)
        return True
    except ZoneInfoNotFoundError:
        return False
