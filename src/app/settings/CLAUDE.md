# Settings 모듈 컨벤션

이 디렉토리(`src/app/settings/`)에서 작업할 때 적용되는 컨벤션. 루트 `CLAUDE.md`의 Key Conventions에서 이관됨.

- **국가 → tz 매핑**: ISO 3166-1 alpha-2 전 249개국 지원 (`pycountry`). 국가→IANA tz 옵션은 `pytz.country_timezones` (CLDR-derived) 사용. 단일 tz 국가(예: KR, JP, FR)는 `country` 만으로 자동 결정, 다중 tz 국가(예: US, RU, BR)는 IANA `timezone` 명시 필수. 신규 국가/tz 추가는 `pytz`/system tzdata 업데이트로 자동 반영 — 코드 수정 불필요. 국가 입력 핸들러는 `shared/domain/utils/timezone.py`의 `is_supported_country`, `country_timezone_options`, `resolve_timezone` 사용. **`region` 컬럼은 deprecated**: 신규 입력 받지 않음, 기존 DB 컬럼은 호환 위해 유지.
- **국가 변경 이력**: `user_country_history` 테이블에 (country, region, timezone, source, created_at) 기록. `source`: `registration` / `oauth_onboarding` / `settings_update`. 회원가입 시점 1행 자동 생성. `UpdateCountryUseCase` 는 실제 값이 변경된 경우에만 row 추가.
