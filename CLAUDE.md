# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Pre-Implementation Workflow (REQUIRED)

코드를 수정하는 모든 요청(기능 추가, 리팩토링, 버그 수정 등)에서 **반드시 아래 순서를 따른다.**

1. **토큰 최소화 작업 진행** - 사용자의 prompt에서 필요한 부분만을 걸러내어 입력 토큰을 최적화 한다.

2. **계획을 먼저 제시한다** — 구현 전에 다음 항목을 포함한 계획을 작성한다:
   - develop.md를 통해 현재 프로젝트 구조와 컨벤션을 검토한다.
   - 수정할 파일 목록과 각 파일에서 변경할 부분
   - 신규 생성할 파일과 각 파일에 담을 코드 내용
   - 사용할 기술 스택 및 라이브러리 (기존과 동일하면 명시)
   - 이 방식을 선택한 이유와 대안 대비 장점

3. **사용자 피드백을 기다린다** — 계획을 제시한 후 승인 또는 수정 요청을 받을 때까지 코드를 작성하지 않는다.

4. **피드백 반영 후 구현한다** — 승인이 나면 계획대로 구현한다:
   - 구현 중 계획과 달라지는 부분이 생기면 먼저 알린다. 
   - 구현 후 사용자의 요청과 계획과 일치하며 컨벤션 및 정책을 어기지 않았는지 확인을 위해 서브 ai로 다른 세션의 sonnet 모델을 통해 검증한다.
   - 검증 후 불일치 부분이나 보완할 부분이 생길 시 다시 해당 부분을 보완하기 위해 다시 구현하고, 다시 검증한다.
   - 검증이 완전히 통과되었을 시 다음 단계로 진행된다.
   - 구현 후 변경된 사항은 api.yaml, develop.md, claude.md 수정이 필요하면 수정한다. 이때 수정은 컨벤션이나 정책에 대한 변경은 사용자의 승인을 구한 뒤에 진행한다.

> 단순 질문, 코드 설명, 현황 파악 요청은 이 절차를 따르지 않는다.

---

## Harness

코드를 수정하는 작업(기능 추가, 리팩토링, 버그 수정)을 시작할 때는 `harness/README.md` 를 먼저 읽고 그 **로딩 규칙**을 따른다 — 작업 유형을 먼저 분류하고, 필요한 파일만 읽는다(무조건 전부 읽지 않는다).

- `harness/mission.md` — AI 의 최우선 목표/성공 기준 (아래 `@import` 로 항상 로드)
- `harness/feature-checklist.md` — 새 기능/엔드포인트 추가 시 레이어별 체크리스트
- `harness/review-checklist.md` — 구현 완료 후 자기검증(reflection)

> 강제력이 필요한 규칙(Model Selection, Pre-Implementation Workflow)은 위 섹션에 그대로 유지된다. harness 는 상세 체크리스트를 **해당 작업일 때만** 로드해 컨텍스트 비용을 아낀다.

@harness/mission.md

---

## Project Overview

**ARCHIVE-BE** — 개인 생산성 및 회고 관리 백엔드 (FastAPI, Python 3.12)

Clean Architecture 패턴 적용: `Domain → Application → Infrastructure → Presentation`

## Tech Stack

| 분류 | 기술 |
|---|---|
| Web Framework | FastAPI (async) |
| ORM | SQLAlchemy 2.0 (async) |
| DB | PostgreSQL |
| Cache / Queue broker | Redis |
| Background tasks | Celery + celery-aio-pool |
| DI Container | Dishka |
| Auth | python-jose (JWT), pwdlib (argon2) |
| HTTP Client | httpx |
| AI | Google Gemini (google-genai) |
| Email | aiosmtplib |
| Logging | structlog |
| Validation | Pydantic v2 |
| Migration | Alembic |

## Project Structure

```
src/app/
├── auth/           # 인증 (이메일, OAuth, JWT)
├── user/           # 유저 도메인
├── todo/           # Todo CRUD
├── retrospective/  # 회고 엔트리 + AI 요약
├── notification/   # 알림 (SSE 포함)
├── settings/       # 유저 설정
├── github/         # GitHub 저장소 연결 (OAuth 토큰 재사용)
├── search/         # Todo + 회고 entry 통합검색 (자체 도메인/인프라 없음, 기존 repo 조합만)
├── worker/         # Celery 태스크
└── shared/         # 공통 인프라 (DI, config, auth, DB, error handling)
```

## Module Structure Convention

각 모듈은 아래 레이어 구조를 따른다:

```
{module}/
├── domain/
│   ├── models/         # 엔티티, Value Object
│   ├── repositories/   # 리포지터리 인터페이스 (ABC)
│   └── exceptions/     # 도메인 예외
├── application/
│   ├── dtos/           # Command / Query DTO
│   └── use_cases/      # Use Case (비즈니스 로직)
├── infrastructure/
│   └── persistence/
│       ├── models/     # SQLAlchemy ORM 모델
│       └── repositories/  # 리포지터리 구현체
└── presentation/
    ├── requests/       # Pydantic 요청 스키마
    ├── responses/      # Pydantic 응답 스키마
    └── router.py       # FastAPI 라우터
```

## API Endpoints

모든 엔드포인트는 `/api/v1` prefix를 가지고, 수정할 시 v2로 변경한다.

| 모듈 | 엔드포인트 |
|---|---|
| Auth | `POST /auth/email/verify/send`, `/confirm`, `/register`, `/login`, `/logout`, `/token/refresh` |
| Auth | `POST /auth/password/reset/request`, `/auth/password/reset/confirm` |
| Auth | `GET /auth/me`, `PATCH /auth/me` |
| Auth | `GET /auth/oauth/{provider}/authorize`, `/callback`, `POST /auth/oauth/{provider}/link/init`, `POST /auth/oauth/onboarding` |
| Auth | `GET /auth/sessions`, `DELETE /auth/sessions`, `DELETE /auth/sessions/{sessionId}` (활성 세션 관리) |
| Todo | `GET/POST /todos`, `PATCH/DELETE /todos/{id}` |
| Entry | `GET/POST /entries`, `GET /entries/paginated`, `GET/PUT/DELETE /entries/{id}`, `PATCH /entries/{id}/folder` |
| Folder | `POST /folders`, `GET /folders/contents`, `PATCH/DELETE /folders/{id}` (중첩 폴더로 회고록 정리) |
| Search | `GET /search` (Todo + daily entry 통합검색) |
| Summary | `POST /summaries/generate`, `GET /summaries/readiness`, `GET /summaries`, `GET /summaries/{id}`, `GET /summaries/{id}/stream` |
| Notification | `GET /notifications/stream`, `GET /notifications`, `PATCH /notifications/read-all`, `PATCH /notifications/{id}/read`, `DELETE /notifications/{id}`, `DELETE /notifications` |
| Settings | `GET/PUT /settings`, `PATCH /settings/country`, `PATCH /settings/timezone`, `GET /settings/countries/{code}/timezones` |
| GitHub | `GET /github/connection`, `GET /github/repositories/available`, `GET/POST/DELETE /github/repositories`, `POST /github/repositories/sync-all`, `PATCH/DELETE /github/repositories/{id}` |
| GitHub | `GET /github/commits` (지정 날짜 / 기본=오늘, public repo only, failed repo 포함), `POST /github/retrospectives/push` |
| RetroTemplate | `GET/POST /templates`, `PATCH/DELETE /templates/{id}`, `POST /templates/{id}/reset`, `PUT /templates/active` |
| Topic | `GET/POST /topics`, `PATCH/DELETE /topics/{id}`, `GET /topics/{id}/stats`, `GET /topics/{id}/sources` |
| Topic | `GET /topics/{id}/digest`, `POST /topics/{id}/digest/generate`, `GET /topics/{id}/digest/stream` (SSE) |

## API Contract — Single Source of Truth

- `api.yaml`은 API 응답/에러 규약의 **Single Source of Truth(SST)** 다.
- 백엔드 매핑(`shared/infrastructure/errors/handler.py`의 `_STATUS_MAP`)과 `api.yaml`이 충돌하면, **`api.yaml`을 기준으로 백엔드를 맞춘다.** 거꾸로가 아니다.
- 새 도메인 예외를 추가했다면 반드시:
  1. `_STATUS_MAP`에 HTTP 상태 코드 매핑 추가
  2. `api.yaml`의 해당 엔드포인트 `x-error-codes`에 코드 명시
  3. `api.yaml`의 공통 응답(`Unauthorized_401`, `Conflict_409` 등) description의 코드 목록에 추가
- 인증 관련 응답은 HTTP 표준 준수:
  - `401 Unauthorized` — 토큰 만료/무효/누락/자격증명 불일치 (FE는 `401 + AUTH_TOKEN_EXPIRED`에서만 자동 refresh 트리거)
  - `400 Bad Request` — 요청 자체의 도메인 조건 위반 (예: 이메일 미인증)
  - `422 Unprocessable Entity` — Pydantic 스키마/타입 검증 실패 (자동)

## Key Conventions

- **DI 등록**: 신규 리포지터리/유스케이스는 반드시 `shared/infrastructure/container/providers.py`에 `@provide`로 등록
- **라우터 등록**: `main.py`의 `create_app()`에 `app.include_router()` 추가
- **응답 형식**: `ApiResponse[T]` 래퍼 사용 (`shared/presentation/schemas/response.py`)
- **인증**: 인증이 필요한 엔드포인트는 `current_user: UserContext = Depends(get_current_user)` 사용
- **DB 마이그레이션**: 스키마 변경 시 `migrations/versions/` 에 Alembic 파일 추가
- **사용자 타임존**: 사용자별 `users.timezone`(IANA tz) 보유. 모든 기간 계산("오늘", "이번 주" 등)은 이 tz 기준으로 처리한다. 절대 서버 UTC 기준으로 계산하지 않는다. `shared/domain/utils/period.py`의 `today_in_tz(tz)`, `now_in_tz(tz)` 사용.
- **회고 템플릿 정책**: `retro_templates` 테이블에 retro_type별 마크다운 템플릿 저장. 회원가입/OAuth 온보딩 시 기본 4종(daily/weekly/monthly/yearly, `is_default=true`) 자동 시드 (`SeedRetroTemplatesUseCase`). 활성 선택은 `user_settings.active_retro_template_ids` (JSONB). 기본 표준 본문은 `retrospective/domain/constants/retro_template_defaults.py`. `is_default=true` 삭제 불가(400). 활성 템플릿 삭제 시 기본 템플릿으로 자동 폴백. `POST /templates/{id}/reset` 으로 기본 템플릿 내용 복원 가능 (커스텀 불가). 에러 코드: `TEMPLATE_NOT_FOUND`(404), `TEMPLATE_DEFAULT_NOT_DELETABLE`(400), `TEMPLATE_TYPE_MISMATCH`(422), `TEMPLATE_NAME_DUPLICATED`(409).
- **Todo 시간 저장 정책**: `todos.start_time` / `todos.end_time` 은 UTC `TIMESTAMPTZ` 로 저장. 사용자 로컬 시각 복원을 위해 생성 시점 IANA timezone 을 `todos.timezone`(`VARCHAR(50)`) 에 함께 저장 (스냅샷). FE 는 로컬 시각을 UTC 로 변환해 전송하고, 응답의 `timezone` 으로 역변환. `start_time` 또는 `end_time` 이 non-null 이면 `timezone` 필수 (422). IANA 검증은 `shared/domain/utils/timezone.py`의 `validate_timezone` 사용.
- **Todo due_date_key 정책**: `todos.due_date_key` (`VARCHAR(10)`, nullable) — 선택적 마감일(포함, YYYY-MM-DD). `due_date_key >= date_key` 제약 (422). POST: Pydantic model_validator에서 검증. PATCH: `omit=unchanged`, `null=clear`, `string=set` 패턴(UNSET sentinel). Pydantic 레벨에서 `date_key`가 같은 요청에 포함된 경우만 체크, 나머지는 `UpdateTodoUseCase._apply_patch`에서 `RequestValidationError` 발생. 반복 Todo exception row(`_materialize_and_update`) 및 following 분리(`_update_following`) 시 source/master의 `due_date_key` 상속.
- **국가 → tz 매핑**: ISO 3166-1 alpha-2 전 249개국 지원 (`pycountry`). 국가→IANA tz 옵션은 `pytz.country_timezones` (CLDR-derived) 사용. 단일 tz 국가(예: KR, JP, FR)는 `country` 만으로 자동 결정, 다중 tz 국가(예: US, RU, BR)는 IANA `timezone` 명시 필수. 신규 국가/tz 추가는 `pytz`/system tzdata 업데이트로 자동 반영 — 코드 수정 불필요. 국가 입력 핸들러는 `shared/domain/utils/timezone.py`의 `is_supported_country`, `country_timezone_options`, `resolve_timezone` 사용. **`region` 컬럼은 deprecated**: 신규 입력 받지 않음, 기존 DB 컬럼은 호환 위해 유지.
- **AI 자동 요약 스케줄링**: Celery beat은 매시간 정각 단일 dispatcher(`dispatch_summaries_for_tz`)만 발사. 각 사용자의 현지 1am 도달 시 fan-out. `last_summary_date_local`로 DST 중복 방지. `SUMMARY_JITTER_SECONDS` 환경 변수로 부하 분산 폭 제어 (기본 1800s).
- **AI 요약 데이터 소스 정책**: 모든 경로(수동/자동)에서 단일 task `worker.generate_summary` 사용. summary_type 별 데이터 소스는 `retrospective/infrastructure/ai/strategies.py` 의 strategy 가 결정한다.
  - **weekly**  : 그 주의 일일 entry + 그 주의 **`in-progress` / `done` 상태 todo** (`EntriesAndTodosStrategy`). `not-start` todo 는 제외.
  - **monthly** : 주 단위 하이브리드 — weekly summary 있으면 사용, 없으면 그 주 entries. weekly 가 있어도 갱신 이후 추가된 entry 가 있으면 자동 첨부 (`MonthlyHybridStrategy`, 방식 B)
  - **annual**  : 월 단위 2단계 하이브리드 — monthly summary 있으면 사용, 없으면 그 달의 weekly summaries 로 보강 (`AnnualHybridStrategy`). 둘 다 없으면 해당 월 스킵
  - 공통 골격(T1 mark in_progress / AI 호출 / T2 complete+notify) 은 `worker/tasks/generate_summary.py` 에 단일 구현
- **AI 프롬프트 / 출력 포맷 정책**: 시스템 instruction 은 **영어**로 통일 (`prompt_builder.py`). 출력 콘텐츠 언어는 사용자 `user_settings.locale` 기반 (`ko`→Korean, `en`→English, 매핑 없으면 raw locale 그대로 전달 — best effort). **출력 포맷은 마크다운 문자열** — `response_schema` 없이 `text/plain` 으로 받는다. 사용자 템플릿이 있으면 그 블록 구조(헤딩/불릿/번호목록/체크박스/인용구 등)를 그대로 따르도록 프롬프트로 지시한다. 템플릿 없으면 기본 4-섹션 마크다운. DB 저장 컬럼: `retro_summaries.content TEXT`. API 응답: `SummaryContentResponse.markdown: string`. FE 는 Tiptap 마크다운 확장으로 렌더링한다. `response.text is None` (safety filter / blocked candidates) 면 `SummaryInvalidStateException` raise 후 FAILED 처리 — autoretry 대상 아님.
- **사용자 자동 요약 템플릿 (1:N + 활성 선택, A안)**: `user_summary_templates` 테이블에 summary_type 별 markdown 템플릿을 다수 저장 (도메인 `UserSummaryTemplate`, repo `UserSummaryTemplateRepository`). 활성 ID 는 `user_settings.active_summary_template_ids` (JSONB) 에 summary_type → template_id 매핑. 한 (user, summary_type) 안 이름 중복 금지 (DB 유니크 인덱스 + use case 검증). 개수 한도는 env `SUMMARY_TEMPLATE_MAX_PER_TYPE` (기본 5, `shared/infrastructure/config/retrospective.py`). 활성 ID 가 가리키는 템플릿이 삭제·summary_type 어긋남 → worker 가 시스템 기본 자동 fallback (`generate_summary.py`). **활성 템플릿은 삭제 차단** (`SummaryTemplateInUseException`) — 활성 보호. 활성 변경은 `PUT /settings/auto-summary/active` (부분 갱신: 미전송 unchanged, 명시 null 은 비활성화). 사용자 템플릿은 `<USER_TEMPLATE>` 태그로 격리되어 시스템 프롬프트에 첨부 — Gemini 가 그 블록 구조를 그대로 따른다 (출력 언어 변경 불가, 시스템 규칙 우선). 4000자 제한. 자동 요약 알림 텍스트는 locale 분기 (`generate_summary.py:_NOTIFICATION_TEXT`).
- **AI 요약 생성 사전 점검 (`GET /summaries/readiness`)**: monthly/annual 만 지원. **entry 밀도** 기반으로 측정 (child summary 존재 여부 아님). monthly = 그 달 일수 중 entry 있는 날 수, annual = 12 중 entry 있는 월 수. `completenessRatio < 0.7` 이면 `recommendation: "insufficient"` → FE 가 사용자에게 다이얼로그로 확인 받음. 정책은 `READINESS_THRESHOLD` 상수 (`get_summary_readiness.py`).
- **회고 엔트리 조회 정책 (`GET /entries`)**: `retroType` 만 지정(`from`/`to` 없음) 시 **오늘 기준 최근 30일만** 반환(`DEFAULT_HYDRATION_DAYS`, `get_entries.py`) — 초기 하이드레이션이 무제한 전체 이력을 반환하던 과거 버그 수정. `from`+`to` 지정 시 최대 366일(Todo 와 동일 컨벤션), 날짜 포맷 오류·범위 초과는 422.
- **회고록 목록 페이지네이션 (`GET /entries/paginated`)**: `retroType` **옵션**(daily/weekly/monthly/yearly) — daily 는 `journal_entries`, weekly/monthly/annual 은 **`retro_summaries`**(AI 생성 요약)에서 조회한다(소스 테이블이 갈림). **미지정 시 두 소스를 합쳐 최신순으로 정렬한 "전체" 뷰** — 전역 상위 `page*size` 개를 커버하려면 각 소스에서 상위 `page*size` 개씩만 가져오면 충분하다는 성질(어느 한쪽이 top-K 를 전부 차지해도 K 를 못 넘음)을 이용해, 전체 이력을 훑지 않고도 정확히 페이지 슬라이스한다(`GetEntriesPageUseCase._execute_merged`). 병합 정렬 기준은 `created_at`(레코드 생성 시각)이 아니라 `date_key`/`period_start`(회고 대상 날짜) — 공용 헬퍼 `retrospective/domain/utils/entry_ordering.py`의 `merge_sorted_desc` 사용(`GET /folders/contents` 의 "전체" 뷰와 동일 로직 공유). 응답 각 항목에 `isSummary`(요약 여부) + `status`(요약 전용: pending/in_progress/completed/failed) 필드 포함. 요약은 title 이 없어 `"{periodStart} ~ {periodEnd}"` 를 기본 타이틀로 채움(FE 가 자체 라벨로 대체 가능). `githubPush` 는 이 엔드포인트에서 항상 키가 존재(nullable) — `GET /entries` 와 달리 비개발자/GitHub 미연결 사용자도 키 자체는 옴(값은 null). `q` 파라미터로 검색 가능(daily 는 `content_tsv` full-text, summary 는 `content`/`edited_content` ILIKE — summary 는 사용자당 연 최대 ~65건이라 tsvector 불필요 판단). 기본 10개씩, 최대 50개.
- **nav 통합검색 (`GET /search?q=`)**: Todo(`title_tsv`)와 daily entry(`content_tsv`)를 `asyncio.gather` 로 동시 조회, `{ todos, entries }` 로 타입별 분리 반환(관련도 점수가 서로 비교 불가능해 억지로 합치지 않음). 각 타입 상위 `limit`개(기본 5, 최대 20). `src/app/search/` 신규 모듈 — 자체 도메인/인프라 레이어 없이 기존 `ITodoRepository`/`IJournalEntryRepository` 를 조합하는 순수 aggregator.
- **회고록 폴더**: `folders` 테이블(self-referencing `parent_folder_id`, adjacency list — 무제한 중첩, 순환참조는 이동 유스케이스에서 조상 체인 순회로 검증)로 daily/weekly/monthly/yearly 회고록(둘 다 `journal_entries`/`retro_summaries`에 nullable `folder_id`) 을 정리한다. 폴더 삭제 시 하위 폴더·안의 회고록은 삭제되지 않고 최상위로 orphan(`ON DELETE SET NULL`, 조부모 승격 아님). `GET /folders/contents`(folderId 생략 시 root)는 직계 하위 폴더(`folders`)와 직계 회고록(`entries`)을 분리 반환(search 의 `{todos, entries}` 분리와 동일 이유) — `retroType` 생략 시 4개 타입을 합친 "전체" 뷰, 지정 시 그 타입만. 회고록 이동은 `PATCH /entries/{id}/folder?retroType=` — `retroType` 필수(두 소스 테이블 id 공간이 달라 라우팅에 필요, paginated 컨벤션과 동일).
- **AI 요약 생성 한도 (사용자별 Redis sliding window)**: 7일 rolling window 로 weekly=10, monthly=3, annual=1 회 제한. Redis Sorted Set (`summary:usage:{user_id}:{type}`) 으로 구현. 실제 AI 호출이 enqueue 되는 경로(신규 / FAILED 재시도 / `?force=true` 재생성)에만 카운트 — COMPLETED 그대로 반환 / 409 충돌은 카운트 안 함. 한도 초과 시 `429 RETRO_SUMMARY_RATE_LIMIT_EXCEEDED` + `details[0]` 에 `{summaryType, limit, windowSeconds, retryAfterSeconds}`. FE 사전 조회는 `GET /summaries/usage`. `POST /summaries/generate?force=true` 는 COMPLETED 도 강제 재생성. 한도/윈도우는 `retrospective/infrastructure/cache/summary_rate_limiter.py` 상수.
- **주제(Topic) 매칭 재사용 정책**: 주제 ↔ 회고/할일 매칭은 **저장하지 않고** 매번 벡터 검색으로 구한다(주제 이름·설명 임베딩 → pgvector 코사인). digest 생성 워커와 요청 경로(`GET /topics`, `/stats`, `/sources`)가 **같은 규칙**을 공유하도록 `topic/application/services/topic_matcher.py`의 `TopicMatcher`로 단일화했다. limit 만 갈린다 — 워커는 프롬프트 길이 때문에 `topic_search_limit`(50), 통계/소스는 `topic_stats_match_limit`(1000). 결과는 `TopicStatsCache`(Redis, key `topic:match:{topic_id}:{sha1(name|description)[:12]}`, TTL `topic_stats_cache_ttl_seconds` 기본 300초)에 캐시되어 세 엔드포인트가 공유 — 목록 20개를 그려도 캐시 히트 시 임베딩 호출 0회, 미스는 `embed_batch` 로 한 번에 처리. 능동 무효화 없이 TTL 만료에만 의존하되, 키에 이름·설명 해시를 섞어 `PATCH /topics/{id}` 직후 stale 매칭이 나가지 않게 한다. **캐시 미스 stampede 방지**: 같은 topic 을 동시에 여러 요청(다른 탭, 중복 새로고침 등)이 미스하면 각자 임베딩 API + DB 를 중복 호출한다 — `TopicStatsCache.lock()`(Redis `SET NX`, TTL `topic_match_lock_ttl_seconds` 기본 30초)으로 한 요청만 계산(single-flight)하고, 락을 못 얻은 요청은 `wait_for()` 로 그 결과가 캐시에 쓰이길 최대 `topic_match_wait_timeout_seconds`(기본 5초) 기다렸다가 재사용한다. 타임아웃까지도 결과가 없으면(보유자 크래시 등) 락 없이 직접 계산해 안전망 역할을 한다 — 최악의 경우에도 무한 대기하지 않는다. 한 요청 안에서 여러 topic 이 함께 미스하는 보통의 경우(첫 로딩 등)에도 topic 마다 락을 시도하지만, 경합이 없으니 매번 그 자리에서 즉시 획득되고 결과는 그대로 `embed_batch` 로 한 번에 처리된다 — 이 락이 절감하는 것은 **동시 요청 간의 중복 계산**이고, genuine miss 1건 자체의 비용은 아래 "매칭 경로 컬럼 프로젝션" 이 따로 줄인다. **주의**: `todo_counts` 는 매칭 규칙상 `not-start` 를 제외하며, 임베딩은 `embed-stale-periodic` beat(5분, `default` 큐)이 채우므로 방금 쓴 글은 지연 반영된다.
- **회고 임베딩 커버리지 정책**: **본문이 있는 회고는 반드시 청크를 최소 하나 갖는다** — 임베딩이 없으면 벡터 검색에 걸리지 않아 주제 집계·digest 어디에도 나타나지 않기 때문이다. `embed_stale.py` 의 `topic_chunk_min_chars`(20자)는 "이 회고를 집계할지"가 아니라 **긴 회고 안에서 의미 없는 짧은 단락(제목, "끝" 등)을 걸러낼지**만 정한다. 모든 단락이 그 미만이라 결과가 비면 본문 전체를 하나의 의미 단위로 보고 길이 상한만 적용하는 폴백이 돈다(임계값을 0 으로 낮추지 않는 이유 — 두 글자 단락이 각각 독립 임베딩이 되면 매칭에 잡음이 된다). 청크는 항상 `topic_chunk_max_chars` 이하다 — `". "` 로 안 쪼개지는 긴 단락(마침표 뒤 줄바꿈만 있는 한국어 글)도 글자 수로 끊는다. 본문이 공백뿐인 회고만 청크가 없다.
- **임베딩 누락 자가 복구**: `embedding_queue` 는 회고/할일 생성·수정 라우터에서만 채워지므로, 워커 다운·큐 등록 실패·기능 도입 이전 데이터는 재시도 경로가 없어 영구 누락된다. `embed_stale_task` 는 큐를 비운 뒤 `enqueue_entries_missing_chunks`(상한 `_RECONCILE_LIMIT`=100)로 **청크 없는 회고를 되돌려 넣고 한 번 더 드레인**한다 — 다음 beat 를 기다리지 않는다. 공백 본문 회고는 대상에서 제외한다(넣어도 청크가 안 생겨 매 주기 되돌아오는 무한 churn 이 된다). **주의**: 이 제외 조건은 파이썬 `str.strip()` 과 정확히 같은 문자 집합이어야 한다 — Postgres 의 `[[:space:]]` 는 NBSP(U+00A0)·FIGURE SPACE(U+2007) 등을 공백으로 치지 않아 `\S` 를 쓰면 "DB 는 내용이 있다고 보는데 청킹은 아무것도 못 만드는" 회고가 영원히 되돌아온다. 패턴은 `chunk_repo.py` 의 `_NON_BLANK_PATTERN`. 그리고 `_process_batch` 는 `len(items)` 가 아니라 **큐에서 실제로 없어진 수**를 반환해야 한다 — 영구히 실패하는 항목이 하나라도 있으면 `_drain` 의 `while count != 0` 이 그 항목을 무한히 다시 꺼낸다. `embed_stale` 은 요약 dispatcher·캘린더 sync 와 `default` 큐를 concurrency 2 로 공유하므로, 물리면 그 두 스케줄이 통째로 멈춘다.
- **매칭 경로 컬럼 프로젝션**: 주제 매칭(`TopicMatcher._resolve`)은 "어떤 회고·할일이 묶이는가" 만 필요하다 — 회고는 `id/title/date_key/retro_type` 4개, 할일은 `id/title/date_key/status/tags` 5개(캐시 페이로드 `MatchedEntry`/`MatchedTodo` 모양 그대로). 그래서 이 경로는 엔티티를 통째로 싣지 않는다: 회고 본문 `content` 와 전문검색 벡터 `content_tsv`, 할일의 반복 규칙·캘린더 push 상태 컬럼은 **SELECT 하지 않는다** (읽기 모델 `JournalEntryMeta`/`TodoMeta`, 조회는 `find_meta_by_ids`). 벡터 검색도 매칭용은 id 만 받는다 (`search_similar_entry_ids` / `search_similar_todo_ids`) — 청크 본문 `text` 를 읽는 곳은 digest 워커뿐이라 그쪽만 `search_similar` 를 쓴다. **상한 단위**: `search_similar_entry_ids` 의 `limit`(`topic_stats_match_limit`)은 **회고** 상한이다 — `GROUP BY entry_id ORDER BY min(거리)` 로 회고마다 가장 가까운 청크 기준 상위 N 개를 고른다. 청크 상한이 아닌 이유는 청크가 단락 길이에 따라 회고당 2~4개로 갈리는 내부 단위인데 사용자에게 보이는 건 "회고 N건" 이기 때문이다 — 청크로 자르면 글을 길게 쓰는 사용자일수록 천장이 낮아지고(회고당 4청크면 250건, 2청크면 500건), 청크가 많은 긴 회고 하나가 다른 회고를 목록에서 밀어낸다. 반면 digest 프롬프트용 `search_similar`/`topic_search_limit` 은 **여전히 청크 상한**이다 — 그쪽은 프롬프트 길이 제약이라 청크가 맞는 단위다. 캐시 페이로드 모양은 그대로라 세 엔드포인트 공유는 유지된다.
- **주제 벡터 검색 구현 규약**: pgvector 검색은 raw `text()` 로 쓰지 않는다 — SQLAlchemy 의 바인드 파서가 `:emb::vector` 처럼 이름 뒤에 콜론이 붙으면 캐스트로 보고 바인딩을 건너뛰어, 파라미터가 문자 그대로 DB 로 나가 구문 오류가 난다. `Vector` 컬럼의 `cosine_distance()` ORM 표현식으로 조립한다(`topic/infrastructure/persistence/repositories/chunk_repo.py`). 유사도 임계값은 `거리 <= 1 - threshold` 로 세워 `<=>` 와 HNSW(`vector_cosine_ops`) 인덱스를 그대로 태운다. 결과에 `embedding` 컬럼은 **싣지 않는다** — 호출자가 읽지 않는데 행마다 768 float 이 딸려온다(읽기 모델 `SimilarChunk`/`SimilarTodo`). 그리고 매칭 경로(`TopicMatcher._resolve`)는 벡터 검색 2회 + 그 결과의 `find_meta_by_ids` 2회 전체를 `ITopicMatchTransaction.nested()` (SAVEPOINT) 하나로 감싼다 — 벡터 검색만 감싸면 뒤따르는 엔티티 조회 실패가 여전히 새어나간다. Postgres 는 문장 하나가 깨지면 트랜잭션 전체를 폐기하므로, 이 가드가 없으면 `GetTopicsUseCase` 처럼 실패를 삼키고 degrade 하는 호출자가 뒤이은 조회(예: digest watermark)에서 InFailedSQLTransaction 으로 500 을 낸다. 응용 계층은 세션을 직접 들고 있지 않으므로 좁은 포트로만 노출한다 — 인터페이스는 `topic/domain/repositories/repository.py`의 `ITopicMatchTransaction`, 구현은 `topic/infrastructure/persistence/transaction.py`의 `SqlAlchemyTopicMatchTransaction` (DI 는 다른 topic 리포지터리와 같은 요청 스코프 세션을 주입).
- **주제 정리 진행률 SSE**: `generate_digest_task` 가 프롬프트에 소스를 접어 넣으며 `{"status":"in_progress","processed":N,"total":M}` 를 `topic_digest_progress_batch_size`(기본 5) 단위로 발행한다. `total` 은 **이번 생성에 투입되는 소스 수**(엔트리 단위 + 할일)로, 최초·재생성 모두 주제 전체를 읽으므로 보통 `/stats` 합계와 일치한다(아주 큰 주제만 `topic_search_limit` 상한에 걸려 작아진다). **주의**: #10 이후 두 값의 단위가 갈렸다 — digest `total` 은 여전히 `topic_search_limit`(200 **청크**) 에 묶이지만 `/stats` 는 `topic_stats_match_limit`(1000 **회고**) 기준이라 사실상 안 막힌다. 청크 200개(회고 60~100건) 미만의 보통 주제에선 여전히 일치하지만, 그 이상 큰 주제에선 예전보다 격차가 훨씬 크게 벌어진다. 라우터는 terminal(`completed`/`failed`)에서만 스트림을 닫는다.
- **주제 정리 재생성 범위 = 항상 전체**: 재생성도 최초 생성과 같은 경로로 **주제 전체 소스를 다시 읽어** 새로 쓴다 (`since_date_key=None`). 과거에 watermark 이후 증분만 읽던 최적화는 재생성할수록 문서가 최근 내용만 다루도록 좁아지는 문제가 있어 제거했다. `watermark_date_key` 는 증분 커서가 아니라 **"이 문서가 언제 기준인가"** 를 뜻하며, FE 배너와 `unreflected_entry_count`(watermark **초과** 날짜의 회고 수 — 정리 당일 회고는 반영된 것으로 본다)의 기준점이다. 프롬프트 상한 `topic_search_limit`(종류별 기본 200 **청크**, 유사도 내림차순 컷)이 곧 문서가 커버하는 범위 — 한 회고가 여러 청크로 쪼개지므로 회고 건수와 1:1이 아니다.
- **주제 정리 재생성 시 content 보존**: 재생성은 `update_status(id, PENDING)` 를 `content=None` 으로 호출하고 repo 가 `if content is not None` 로 가드하므로, **재생성 중에도 실패 후에도 직전 `content` 가 유지**된다(성공 시에만 교체).
- **회고 기본 제목 정책**: `POST /entries` 에서 `title` 이 없거나 공백뿐이면, `PUT /entries/{id}` 에서 빈 문자열이면 서버가 `"{date_key} {회고 종류}"` 로 채운다. 언어는 `user_settings.locale` 기준(`ko`/`en`/`ja`/`zh`, 그 외는 **en 폴백** — `generate_summary.py` 의 `_notification_text` 와 같은 컨벤션). 규칙 본체는 `retrospective/domain/constants/entry_title_defaults.py`. 기존 데이터 마이그레이션은 하지 않는다.
- **`GET /todos/stats?range=all`**: 전체 기간 = `2000-01-01 ~ 오늘`. 상한을 `today` 로 두는 것은 "이미 쌓인" 개수라는 의미에 맞을 뿐 아니라 **안전장치**다 — `date.max` 로 두면 종료일 없는 반복 Todo 마다 `generate_slots_from` 가상 슬롯 루프가 서기 9999년까지 수백만 번 돌아 요청이 멈춘다. `today/week/month` 동작은 불변.
- **Session 보안 정책**: Refresh token = `{sessionId}.{secret}` 형식. 모든 refresh 시 rotation + reuse detection. 폐기된 RT 재등장 시 해당 사용자의 모든 세션 즉시 폐기 + `security` structlog 채널에 `session.refresh_reuse_detected` 로깅. 동시 refresh race 는 `SESSION_GRACE_WINDOW_SECONDS`(기본 5초) grace window 로 흡수 (`session.refresh_grace_hit` 로깅). 세션 정책 본체는 `auth/application/services/session_service.py`. Redis 캐시는 raw CRUD 만 담당 (`auth/infrastructure/cache/auth_token.py`).
- **운영 파라미터 (TTL/window) env 화**: 모든 시간 기반 파라미터는 `.env` 에서 관리한다. `OAUTH_STATE_TTL_SECONDS`, `ONBOARDING_TOKEN_TTL_SECONDS`, `PASSWORD_RESET_TTL_SECONDS`, `PASSWORD_RESET_COOLDOWN_TTL_SECONDS`, `SESSION_GRACE_WINDOW_SECONDS`. 기본값은 `shared/infrastructure/config/auth.py`의 `AuthConfig`. 라우터의 cookie max-age는 별도 env 가 아니라 `refresh_token_expire_days` / `onboarding_token_ttl_seconds`에서 derive — 항상 Redis TTL과 동기화 보장.
- **OAuth Link 흐름**: 로그인된 사용자의 provider 계정 link 는 `POST /auth/oauth/{provider}/link/init` (Bearer) 로 시작. 응답의 `authorizeUrl` 을 FE 가 popup 으로 직접 연다. callback URL 은 일반 로그인과 동일 — state 에 저장된 `link_user_id` 로 분기.
- **OAuth Callback URL**: dev/prod 모두 **FE proxy origin** (예: `http://localhost:5173/api/v1/auth/oauth/{provider}/callback`) 으로 통일. callback HTML 의 `window.opener.postMessage` 가 FE origin 으로 도달해야 origin 검증을 통과한다.
- **국가 변경 이력**: `user_country_history` 테이블에 (country, region, timezone, source, created_at) 기록. `source`: `registration` / `oauth_onboarding` / `settings_update`. 회원가입 시점 1행 자동 생성. `UpdateCountryUseCase` 는 실제 값이 변경된 경우에만 row 추가.
- **GitHub commit 조회 (`GET /github/commits`)**: scope = `user:email,public_repo`. **public repo only** (private repo 는 404 → `failedRepositories`). **모든 branch 조회** — repo 마다 `list_branches` 로 branch 목록 fetch 후 branch 별 `list_commits(sha=branch)` 병렬 호출 → SHA dedup. default branch 외 feature/topic branch 의 commit 도 포함. 응답은 `{ commits, failedRepositories }`. Fatal 에러(`AUTH_TOKEN_INVALID`/`RATE_LIMITED`/`API_UNAVAILABLE`) 는 전체 raise. 사용자 GitHub `login` 과 **verified emails** 는 `oauth_connections.provider_login` / `provider_verified_emails` 에 캐시(lazy backfill — 첫 commit 조회 시 `/user`, `/user/emails` 호출 후 저장).
- **GitHub commit 본인 매칭 정책**: GitHub `?author=` 필터는 사용 안 함. 모든 commit 을 받은 뒤 서버사이드 OR 필터 — `author.login == login` OR `committer.login == login` OR `commit.author.email ∈ verified_emails` OR `commit.committer.email ∈ verified_emails`. gitbash 등 로컬 `git config user.email` 이 GitHub 계정에 verified 등록돼 있으면 본인 commit 으로 잡힘. 정책 본체: `get_commits_by_date.py:_is_user_commit`. `GET /github/connection` 응답의 `hasVerifiedEmails: false` 면 FE 가 재연결 유도.
- **GitHubApiClient**: APP scope 단일 인스턴스 — `httpx.AsyncClient` 멤버 재사용으로 커넥션 풀링. lifespan 종료 시 `close()` 호출 (main.py 의 lifespan 에서 처리).
- **회고록 GitHub push 상태**: `POST /github/retrospectives/push` 성공 시 `retrospective_pushes` 테이블에 `(user_id, period_type, period_key)` 단위로 upsert. `GET /entries`, `GET /entries/{id}`, `GET /summaries`, `GET /summaries/{id}` 응답의 `githubPush` 필드로 노출. 매핑 헬퍼는 `app.github.domain.utils.period_mapping` — `entry_to_period(entry)` / `summary_to_period(summary)`. `RetroType.YEARLY` 는 push API 의 `annual` 로 정규화.

## Environment Setup

```powershell
# 가상환경 활성화 (Windows)
.venv\Scripts\Activate.ps1

# 의존성 설치
pip install -r requirements.txt

# 서버 실행
uvicorn app.main:app --reload

# DB 마이그레이션
alembic upgrade head

# 테스트 / 린트 / 타입 검사 — 모두 저장소 루트에서 실행한다
# (pytest 의 pythonpath, mypy 의 mypy_path 가 모두 상대 경로 "src" 라서)
pytest -q
ruff check .
mypy            # 대상은 pyproject.toml 의 packages=["app"] 에 박혀 있어 인자 불필요

# Celery worker 실행 (ai_tasks 큐 반드시 포함 — worker.generate_summary 가 이 큐로 라우팅됨)
celery -A app.worker.celery_app worker -Q ai_tasks,default --concurrency=3 --loglevel=info

# Celery beat (자동 요약 dispatcher 스케줄러) — schedule 파일은 쓰기 가능한 경로로 지정
celery -A app.worker.celery_app worker --beat -Q default --schedule=/tmp/celerybeat-schedule --loglevel=info

# Celery worker (캘린더 백그라운드 동기화 — calendar 큐 소비자 필수)
celery -A app.worker.celery_app worker -Q calendar --concurrency=3 --loglevel=info
```

> **큐 분리**: `ai_tasks` = AI 요약 task (`worker.generate_summary`, priority=9), `default` = 스케줄 dispatcher (`worker.dispatch_summaries_for_tz` + `worker.sync_all_calendars` beat 발사), `calendar` = 캘린더 백그라운드 동기화 (`worker.sync_all_calendars` dispatcher + `worker.sync_user_calendar` fan-out). worker 를 `-Q` 없이 띄우면 `task_default_queue=default` 만 소비해 요약 task 가 영원히 처리되지 않으니 **`ai_tasks` 를 반드시 포함**한다. 마찬가지로 **`calendar` 큐를 소비하는 worker 가 없으면 백그라운드 캘린더 sync 가 영원히 처리되지 않는다.** docker-compose 는 `worker-ai`(ai_tasks) / `worker-beat`(default+beat) / `worker-calendar`(calendar) 세 컨테이너로 분리되어 있다. 캘린더 sync 는 시간에 민감한 요약 dispatcher 와 무거운 AI 요약 양쪽에서 격리된다.

### 배포 (Production)

로컬 `docker-compose.yml`(build+bind mount+`--reload`+DB 포트 노출)은 그대로 두고, `docker-compose.prod.yml` 오버레이로 배포 차이점만 병합한다:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

- 이미지는 `.github/workflows/build-and-push.yml`(main push / `v*` 태그 push 시 트리거)이 GHCR(`ghcr.io/heiji57/archive-be`)로 빌드·push. `IMAGE_REPO`/`IMAGE_TAG` env var로 다른 레지스트리/태그 지정 가능.
- `docker-compose.prod.yml`은 `!reset`(Compose merge 문법)으로 `build`/`volumes`/`command`(api)/`ports`(postgres, redis)를 제거한다 — 소스 bind mount 없이 이미지에 baked-in 된 코드만 실행되고, DB/Redis 포트는 호스트에 노출되지 않는다(archive-net 내부에서만 api/worker 가 접근).
- `env_file`은 `.env.production` — protected file(`.env.*`)이라 `.env.example`을 복사해 직접 채워야 한다.

## Protected Files (DO NOT READ OR MODIFY)

아래 파일은 절대 읽거나 수정하지 않는다. 코드 작업 중 이 파일들이 필요한 경우 사용자에게 직접 확인을 요청한다.

| 파일 | 이유 |
|---|---|
| `.env` | 실제 시크릿 키, DB 비밀번호 등 민감 정보 포함 |
| `.env.*` (`.env.local`, `.env.production` 등 모든 변형) | 동일한 이유 |

> `.env.example`은 예시 파일이므로 읽기는 허용하나, 수정은 하지 않는다.

---

## Development Notes

- Python 3.12, Black formatter (PyCharm 설정)
- `BaseEntity`: `id: str`, `created_at: datetime`, `updated_at: datetime | None`
- ID 생성: `generate_id("{prefix}")` (UUID7 기반, `shared/domain/utils/id.py`)
- SSE: `sse-starlette` + Redis pub/sub 패턴 (summary, notification 참고)
