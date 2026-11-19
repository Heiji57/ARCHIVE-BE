# Calendars 모듈 컨벤션

이 디렉토리(`src/app/calendars/`)에서 작업할 때 적용되는 컨벤션.

- **사용자 캘린더 ≠ Google 연동**: 이 모듈은 할 일을 묶는 사용자 캘린더(개인·팀·스터디, `/calendars`). Google Calendar 연동은 `google_calendar` 모듈(`/calendar/*`) — 이름이 겹치지 않게 경로를 나눴다.
- **기본 캘린더 = `todos.calendar_id IS NULL`**: 기본 캘린더 행은 이름·색·Google 보내기 여부를 담는 메타다. 할 일이 그 id 를 가리킬 필요가 없고, 캘린더를 지우면 FK `ON DELETE SET NULL` 로 그 할 일이 기본 캘린더로 옮겨진다. 사용자마다 기본 캘린더는 정확히 하나(부분 유니크 인덱스 `uq_calendars_user_default`). 없으면 `ensure_default` 가 목록·생성 때 만든다(마이그레이션 043 이 기존 사용자 몫을 만들었다). 이름은 고정 키 `default` — 표시 이름은 FE 가 locale 로.
- **Google 자동 보내기**: 생성 시 `push_to_calendar` 를 안 보내면 `settings.calendar_auto_push_todo` **그리고** 그 할 일 캘린더의 `push_to_google` 일 때만 보낸다(기본 캘린더만 기본 true). Google 쪽 대상은 여전히 기본(primary) 하나.
- **소유 검사**: 할 일 생성·수정의 `calendar_id` 는 `todo/application/services/calendar_guard.py` 의 `check_calendar_owned` 로 본인 것인지 본다(아니면 404 `CALENDAR_NOT_FOUND`).
- **DI**: 이 모듈은 자체 `CalendarsProvider`(`infrastructure/container/providers.py`)를 `main.py` 의 `make_async_container` 에 등록한다(루트 CLAUDE.md DI 컨벤션). 화면에서 캘린더를 "끄는" 것은 FE 로컬 설정이고, 할 일 조회의 `calendarIds` 거르기는 todo 라우터가 한다.
