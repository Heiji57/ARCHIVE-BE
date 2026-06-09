# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Model Selection (REQUIRED)

코드를 수정하는 모든 요청이 들어오면 **구현 시작 전 반드시 사용할 모델을 확인한다.**

응답 첫 줄에 아래 형식으로 묻는다:

```
사용할 모델을 선택하세요: 1) Haiku  2) Sonnet  3) Opus  (기본값: 2)
```

- 사용자가 **숫자(1·2·3)** 로 답하면 해당 모델로 진행한다.
- 사용자가 **모델 이름**(haiku / sonnet / opus)으로 답해도 동일하게 처리한다.
- 사용자가 **Enter(빈 입력)** 하거나 답하지 않으면 **Sonnet(기본값)** 으로 진행한다.
- 선택된 모델은 `/model` 명령으로 전환할 수 있음을 안내한다.

| 번호 | 모델 | 적합한 상황 |
|---|---|---|
| 1 | Haiku | 단순 CRUD, 보일러플레이트, 빠른 수정 |
| 2 | Sonnet | 일반 기능 구현, 리팩토링 (기본값) |
| 3 | Opus | 복잡한 아키텍처 설계, 어려운 버그, 성능 최적화 |

> 단순 질문, 코드 설명, 현황 파악 요청은 모델 선택을 묻지 않는다.

---

## Pre-Implementation Workflow (REQUIRED)

코드를 수정하는 모든 요청(기능 추가, 리팩토링, 버그 수정 등)에서 **반드시 아래 순서를 따른다.**

1. **계획을 먼저 제시한다** — 구현 전에 다음 항목을 포함한 계획을 작성한다:
   - 수정할 파일 목록과 각 파일에서 변경할 부분
   - 신규 생성할 파일과 각 파일에 담을 코드 내용
   - 사용할 기술 스택 및 라이브러리 (기존과 동일하면 명시)
   - 이 방식을 선택한 이유와 대안 대비 장점

2. **사용자 피드백을 기다린다** — 계획을 제시한 후 승인 또는 수정 요청을 받을 때까지 코드를 작성하지 않는다.

3. **피드백 반영 후 구현한다** — 승인이 나면 계획대로 구현한다. 구현 중 계획과 달라지는 부분이 생기면 먼저 알린다.

> 단순 질문, 코드 설명, 현황 파악 요청은 이 절차를 따르지 않는다.

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

모든 엔드포인트는 `/api/v1` prefix를 가진다.

| 모듈 | 엔드포인트 |
|---|---|
| Auth | `POST /auth/email/verify/send`, `/confirm`, `/register`, `/login`, `/logout`, `/token/refresh` |
| Auth | `POST /auth/password/reset/request`, `/auth/password/reset/confirm` |
| Auth | `GET /auth/me`, `PATCH /auth/me` |
| Auth | `GET /auth/oauth/{provider}/authorize`, `/callback`, `POST /auth/oauth/{provider}/link/init`, `POST /auth/oauth/onboarding` |
| Auth | `GET /auth/sessions`, `DELETE /auth/sessions`, `DELETE /auth/sessions/{sessionId}` (활성 세션 관리) |
| Todo | `GET/POST /todos`, `PATCH/DELETE /todos/{id}` |
| Entry | `GET/POST /entries`, `GET/PUT/DELETE /entries/{id}` |
| Summary | `POST /summaries/generate`, `GET /summaries/readiness`, `GET /summaries`, `GET /summaries/{id}`, `GET /summaries/{id}/stream` |
| Notification | `GET /notifications/stream`, `GET /notifications`, `PATCH /notifications/read-all`, `PATCH /notifications/{id}/read`, `DELETE /notifications/{id}`, `DELETE /notifications` |
| Settings | `GET/PUT /settings`, `PATCH /settings/country`, `PATCH /settings/timezone`, `GET /settings/countries/{code}/timezones` |
| GitHub | `GET /github/connection`, `GET /github/repositories/available`, `GET/POST/DELETE /github/repositories`, `POST /github/repositories/sync-all`, `PATCH/DELETE /github/repositories/{id}` |
| GitHub | `GET /github/commits` (지정 날짜 / 기본=오늘, public repo only, failed repo 포함), `POST /github/retrospectives/push` |

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
- **국가 → tz 매핑**: ISO 3166-1 alpha-2 전 249개국 지원 (`pycountry`). 국가→IANA tz 옵션은 `pytz.country_timezones` (CLDR-derived) 사용. 단일 tz 국가(예: KR, JP, FR)는 `country` 만으로 자동 결정, 다중 tz 국가(예: US, RU, BR)는 IANA `timezone` 명시 필수. 신규 국가/tz 추가는 `pytz`/system tzdata 업데이트로 자동 반영 — 코드 수정 불필요. 국가 입력 핸들러는 `shared/domain/utils/timezone.py`의 `is_supported_country`, `country_timezone_options`, `resolve_timezone` 사용. **`region` 컬럼은 deprecated**: 신규 입력 받지 않음, 기존 DB 컬럼은 호환 위해 유지.
- **AI 자동 요약 스케줄링**: Celery beat은 매시간 정각 단일 dispatcher(`dispatch_summaries_for_tz`)만 발사. 각 사용자의 현지 1am 도달 시 fan-out. `last_summary_date_local`로 DST 중복 방지. `SUMMARY_JITTER_SECONDS` 환경 변수로 부하 분산 폭 제어 (기본 1800s).
- **AI 요약 데이터 소스 정책**: 모든 경로(수동/자동)에서 단일 task `worker.generate_summary` 사용. summary_type 별 데이터 소스는 `retrospective/infrastructure/ai/strategies.py` 의 strategy 가 결정한다.
  - **weekly**  : 그 주의 일일 entry 직접 (`EntriesOnlyStrategy`)
  - **monthly** : 주 단위 하이브리드 — weekly summary 있으면 사용, 없으면 그 주 entries. weekly 가 있어도 갱신 이후 추가된 entry 가 있으면 자동 첨부 (`MonthlyHybridStrategy`, 방식 B)
  - **annual**  : 월 단위 2단계 하이브리드 — monthly summary 있으면 사용, 없으면 그 달의 weekly summaries 로 보강 (`AnnualHybridStrategy`). 둘 다 없으면 해당 월 스킵
  - 공통 골격(T1 mark in_progress / AI 호출 / T2 complete+notify) 은 `worker/tasks/generate_summary.py` 에 단일 구현
- **AI 요약 생성 사전 점검 (`GET /summaries/readiness`)**: monthly/annual 만 지원. **entry 밀도** 기반으로 측정 (child summary 존재 여부 아님). monthly = 그 달 일수 중 entry 있는 날 수, annual = 12 중 entry 있는 월 수. `completenessRatio < 0.7` 이면 `recommendation: "insufficient"` → FE 가 사용자에게 다이얼로그로 확인 받음. 정책은 `READINESS_THRESHOLD` 상수 (`get_summary_readiness.py`).
- **Session 보안 정책**: Refresh token = `{sessionId}.{secret}` 형식. 모든 refresh 시 rotation + reuse detection. 폐기된 RT 재등장 시 해당 사용자의 모든 세션 즉시 폐기 + `security` structlog 채널에 `session.refresh_reuse_detected` 로깅. 동시 refresh race 는 `SESSION_GRACE_WINDOW_SECONDS`(기본 5초) grace window 로 흡수 (`session.refresh_grace_hit` 로깅). 세션 정책 본체는 `auth/application/services/session_service.py`. Redis 캐시는 raw CRUD 만 담당 (`auth/infrastructure/cache/auth_token.py`).
- **운영 파라미터 (TTL/window) env 화**: 모든 시간 기반 파라미터는 `.env` 에서 관리한다. `OAUTH_STATE_TTL_SECONDS`, `ONBOARDING_TOKEN_TTL_SECONDS`, `PASSWORD_RESET_TTL_SECONDS`, `PASSWORD_RESET_COOLDOWN_TTL_SECONDS`, `SESSION_GRACE_WINDOW_SECONDS`. 기본값은 `shared/infrastructure/config/auth.py`의 `AuthConfig`. 라우터의 cookie max-age는 별도 env 가 아니라 `refresh_token_expire_days` / `onboarding_token_ttl_seconds`에서 derive — 항상 Redis TTL과 동기화 보장.
- **OAuth Link 흐름**: 로그인된 사용자의 provider 계정 link 는 `POST /auth/oauth/{provider}/link/init` (Bearer) 로 시작. 응답의 `authorizeUrl` 을 FE 가 popup 으로 직접 연다. callback URL 은 일반 로그인과 동일 — state 에 저장된 `link_user_id` 로 분기.
- **OAuth Callback URL**: dev/prod 모두 **FE proxy origin** (예: `http://localhost:5173/api/v1/auth/oauth/{provider}/callback`) 으로 통일. callback HTML 의 `window.opener.postMessage` 가 FE origin 으로 도달해야 origin 검증을 통과한다.
- **국가 변경 이력**: `user_country_history` 테이블에 (country, region, timezone, source, created_at) 기록. `source`: `registration` / `oauth_onboarding` / `settings_update`. 회원가입 시점 1행 자동 생성. `UpdateCountryUseCase` 는 실제 값이 변경된 경우에만 row 추가.
- **GitHub commit 조회 (`GET /github/commits`)**: scope = `user:email,public_repo`. **public repo only** (private repo 는 404 → `failedRepositories`). 응답은 `{ commits, failedRepositories }`. Fatal 에러(`AUTH_TOKEN_INVALID`/`RATE_LIMITED`/`API_UNAVAILABLE`) 는 전체 raise. 사용자 GitHub `login` 과 **verified emails** 는 `oauth_connections.provider_login` / `provider_verified_emails` 에 캐시(lazy backfill — 첫 commit 조회 시 `/user`, `/user/emails` 호출 후 저장).
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

# Celery worker 실행
celery -A app.worker.celery_app worker --loglevel=info
```

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
