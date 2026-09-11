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
│   ├── container/
│   │   └── providers.py  # 이 모듈 소속 Dishka Provider (해당 모듈의 리포지터리/유스케이스 등록)
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

범용 컨벤션만 여기 남긴다. 모듈별(도메인 정책) 컨벤션은 각 모듈 디렉토리의 `CLAUDE.md`로 이관됐다 — 해당 모듈 작업 시에만 자동 로드된다: `src/app/todo/CLAUDE.md`, `src/app/retrospective/CLAUDE.md`, `src/app/topic/CLAUDE.md`, `src/app/auth/CLAUDE.md`, `src/app/settings/CLAUDE.md`, `src/app/github/CLAUDE.md`, `src/app/search/CLAUDE.md`.

- **DI 등록**: 신규 리포지터리/유스케이스는 그 클래스가 속한 도메인 모듈의 `{module}/infrastructure/container/providers.py`에 `@provide`로 등록(예: `todo` 리포지터리/유스케이스는 `todo/infrastructure/container/providers.py`의 `TodoProvider`). 신규 모듈이면 `main.py`의 `make_async_container()` 호출부에 그 Provider 인스턴스를 추가한다. `shared/infrastructure/container/providers.py`(`SharedProvider`)는 DB 세션 등 특정 도메인에 속하지 않는 공용 인프라 전용 — 도메인 리포지터리/유스케이스를 여기 넣지 않는다. Scope는 각 Provider 클래스의 기본값(대개 `Scope.REQUEST`)을 따르되, 캐시/API 클라이언트처럼 앱 전체에서 싱글턴이어야 하는 것은 메서드 단위 `@provide(scope=Scope.APP)`로 오버라이드한다.
- **라우터 등록**: `main.py`의 `create_app()`에 `app.include_router()` 추가
- **응답 형식**: `ApiResponse[T]` 래퍼 사용 (`shared/presentation/schemas/response.py`)
- **인증**: 인증이 필요한 엔드포인트는 `current_user: UserContext = Depends(get_current_user)` 사용
- **DB 마이그레이션**: 스키마 변경 시 `migrations/versions/` 에 Alembic 파일 추가
- **사용자 타임존**: 사용자별 `users.timezone`(IANA tz) 보유. 모든 기간 계산("오늘", "이번 주" 등)은 이 tz 기준으로 처리한다. 절대 서버 UTC 기준으로 계산하지 않는다. `shared/domain/utils/period.py`의 `today_in_tz(tz)`, `now_in_tz(tz)` 사용.

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

> 프로덕션 배포 절차는 `deploy` 스킬 참고 (`.claude/skills/deploy/SKILL.md`).

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
