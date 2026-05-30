# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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
| Auth | python-jose (JWT), passlib (bcrypt) |
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
| Auth | `GET /auth/me`, `PATCH /auth/me` |
| Auth | `GET /auth/oauth/{provider}/authorize`, `/callback` |
| Todo | `GET/POST /todos`, `PATCH/DELETE /todos/{id}` |
| Entry | `GET/POST /entries`, `GET/PUT/DELETE /entries/{id}` |
| Summary | `POST /summaries/generate`, `GET /summaries`, `GET /summaries/{id}`, `GET /summaries/{id}/stream` |
| Notification | `GET /notifications/stream`, `GET /notifications`, `PATCH /notifications/read-all`, `PATCH /notifications/{id}/read`, `DELETE /notifications/{id}`, `DELETE /notifications` |
| Settings | `GET/PUT /settings` |

## Key Conventions

- **DI 등록**: 신규 리포지터리/유스케이스는 반드시 `shared/infrastructure/container/providers.py`에 `@provide`로 등록
- **라우터 등록**: `main.py`의 `create_app()`에 `app.include_router()` 추가
- **응답 형식**: `ApiResponse[T]` 래퍼 사용 (`shared/presentation/schemas/response.py`)
- **인증**: 인증이 필요한 엔드포인트는 `current_user: UserContext = Depends(get_current_user)` 사용
- **DB 마이그레이션**: 스키마 변경 시 `migrations/versions/` 에 Alembic 파일 추가

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

## Development Notes

- Python 3.12, Black formatter (PyCharm 설정)
- `BaseEntity`: `id: str`, `created_at: datetime`, `updated_at: datetime | None`
- ID 생성: `generate_id("{prefix}")` (UUID7 기반, `shared/domain/utils/id.py`)
- SSE: `sse-starlette` + Redis pub/sub 패턴 (summary, notification 참고)
