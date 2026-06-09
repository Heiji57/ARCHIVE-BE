# ARCHIVE — 백엔드 개발 문서

> AI 코드 어시스턴트 및 개발자가 이 프로젝트에서 착오 없이 개발하기 위한 참고 문서입니다.

---

## 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [기술 스택](#2-기술-스택)
3. [개발 환경 — Docker](#3-개발-환경--docker)
4. [폴더 구조](#4-폴더-구조)
5. [아키텍처 — Clean Architecture + DDD](#5-아키텍처--clean-architecture--ddd)
6. [Domain Layer](#6-domain-layer)
7. [Application Layer](#7-application-layer)
8. [Infrastructure Layer](#8-infrastructure-layer)
9. [Presentation Layer](#9-presentation-layer)
10. [의존성 주입 — dishka IoC Container](#10-의존성-주입--dishka-ioc-container)
11. [에러 처리](#11-에러-처리)
12. [API 응답 형식](#12-api-응답-형식)
13. [크로스 도메인 참조 규칙](#13-크로스-도메인-참조-규칙)
14. [스키마 설계 규칙](#14-스키마-설계-규칙)
15. [Async / Sync 규칙](#15-async--sync-규칙)
16. [데이터베이스](#16-데이터베이스)
17. [Redis 역할 분담](#17-redis-역할-분담)
18. [인증 / 인가](#18-인증--인가)
19. [Celery Worker](#19-celery-worker)
20. [테스트](#20-테스트)
21. [코드 품질](#21-코드-품질)

---

## 1. 프로젝트 개요

**ARCHIVE-BE**는 개발자 생산성 관리 웹 애플리케이션 **ARCHIVE**의 FastAPI 백엔드 서버입니다.

프론트엔드가 Mock으로 처리하던 아래 기능들을 실제로 구현합니다.

| 기능 | 현재 (Frontend Mock) | 구현 목표 |
|---|---|---|
| 인증 | 미구현 | GitHub OAuth / Google OAuth / 이메일+패스워드 + TOTP 2FA |
| 데이터 영속성 | localStorage | PostgreSQL (Todo, 회고, 알림, 사용자) |
| GitHub 커밋 조회 | 가짜 배열 | GitHub API (httpx 경유) |
| AI 요약 생성 | 6초 setTimeout | Anthropic API (Celery 비동기 태스크) |
| 자동 요약 스케줄 | 앱 실행 시 1회 체크 | Celery Beat (주간/월간/연간) |
| 전문 검색 | 없음 | PostgreSQL tsvector |

단일 서버 **모놀리식** 구조입니다. 마이크로서비스 분리는 고려하지 않습니다.

---

## 2. 기술 스택

| 분류 | 기술 |
|---|---|
| 서버 | FastAPI, Uvicorn |
| ORM / 마이그레이션 | SQLAlchemy 2.x (async), Alembic |
| DB 드라이버 | asyncpg |
| 데이터베이스 | PostgreSQL 16 (tsvector 초기 구축) |
| 캐시 / 큐 브로커 | Redis 7 |
| 비동기 워커 | Celery 5 |
| IoC Container | dishka |
| 인증 | python-jose (JWT), pwdlib[argon2] |
| AI | gemini
| 외부 API | httpx (GitHub API, OAuth — async only) |
| 설정 관리 | pydantic-settings |
| 코드 품질 | ruff (lint + format), mypy (타입 체크) |
| 로깅 | structlog |
| 테스트 | pytest, pytest-asyncio, httpx[testclient] |
| 인프라 | Docker, Docker Compose |

---

## 3. 개발 환경 — Docker

Docker Compose로 **server / db / redis / worker** 4개 서비스를 올립니다.

### 서비스 구성

| 서비스 | 이미지 | 포트 | 역할 |
|---|---|---|---|
| `server` | 프로젝트 Dockerfile | 8000 | FastAPI + Uvicorn |
| `db` | postgres:16 | 5432 | PostgreSQL |
| `redis` | redis:7 | 6379 | Celery 브로커 + 앱 캐시 |
| `worker` | 프로젝트 Dockerfile | — | Celery Worker + Beat |

### 자주 쓰는 명령

```bash
# 전체 서비스 실행
docker-compose up -d

# 로그 실시간 확인
docker-compose logs -f server
docker-compose logs -f worker

# 마이그레이션 적용
docker-compose exec server alembic upgrade head

# 새 마이그레이션 파일 생성
docker-compose exec server alembic revision --autogenerate -m "add_todo_table"

# 테스트 전체 실행
docker-compose exec server pytest

# 단일 테스트 파일 실행
docker-compose exec server pytest tests/unit/test_todo_domain.py -v

# 린트 + 포맷
docker-compose exec server ruff check src/
docker-compose exec server ruff format src/

# 타입 체크
docker-compose exec server mypy src/
```

---

## 4. 폴더 구조

Bounded Context별로 내부 레이어를 갖는 **도메인 우선** 구조입니다.

```
src/
└── app/
    ├── user/                        # [Bounded Context] 사용자/인증
    │   ├── domain/
    │   │   ├── models/
    │   │   │   └── user.py          # User, OAuthConnection 엔티티 + VO
    │   │   ├── exceptions/
    │   │   │   └── exceptions.py    # UserNotFoundException 등
    │   │   └── repositories/
    │   │       └── repository.py    # IUserRepository (ABC)
    │   ├── application/
    │   │   ├── use_cases/           # 파일 1개 = 클래스 1개
    │   │   │   ├── create_user.py
    │   │   │   └── connect_oauth.py
    │   │   └── dtos/
    │   │       ├── commands.py
    │   │       └── queries.py
    │   ├── presentation/
    │   │   ├── router.py
    │   │   ├── requests/
    │   │   │   └── requests.py
    │   │   └── responses/
    │   │       └── responses.py
    │   └── infrastructure/
    │       ├── persistence/
    │       │   ├── models/
    │       │   │   └── user_model.py
    │       │   └── repositories/
    │       │       └── user_repo.py
    │       └── external/
    │           └── oauth.py         # GitHub / Google OAuth 처리
    │
    ├── todo/                        # [Bounded Context] 할 일
    │   └── ...
    │
    ├── retrospective/               # [Bounded Context] 회고
    │   └── infrastructure/
    │       └── tasks/
    │           └── summary_task.py  # AI 요약 Celery 태스크 (도메인 귀속)
    │
    ├── notification/                # [Bounded Context] 알림
    │   └── ...
    │
    └── shared/                      # [공통] Cross-Cutting Concerns
        ├── domain/
        │   ├── models/
        │   │   └── base.py          # BaseEntity, UserId, DateKey 등 공통 VO
        │   ├── exceptions/
        │   │   └── base.py          # BaseAppException (순수 Python)
        │   ├── utils/
        │   │   └── id.py            # generate_id()
        │   └── context/
        │       └── user_context.py  # UserContext (현재 로그인 유저 타입)
        ├── presentation/
        │   └── schemas/
        │       └── response.py      # ApiResponse, PaginatedData, PaginationQuery
        └── infrastructure/
            ├── container/
            │   ├── __init__.py
            │   └── providers.py     # dishka Provider (APP/REQUEST scope)
            ├── database/
            │   ├── base.py          # SQLAlchemy DeclarativeBase
            │   └── session.py       # async_sessionmaker 팩토리
            ├── cache/
            │   └── redis.py         # Redis 연결 풀 (DB 0/1/2)
            ├── auth/
            │   ├── jwt.py           # JWT 발급 / 검증
            │   └── password.py      # argon2 해싱 (pwdlib, hardened params)
            ├── errors/
            │   ├── codes.py         # ErrorCode 상수 (도메인별 에러 코드)
            │   └── handler.py       # GlobalExceptionHandler + HTTP 상태 매핑
            ├── logger/
            │   └── setup.py         # structlog 초기화
            └── worker/
                └── celery_app.py    # Celery 앱 인스턴스 + Beat 스케줄

tests/
├── conftest.py
├── factories/                       # 테스트 데이터 팩토리
│   ├── todo_factory.py
│   └── user_factory.py
├── unit/                            # 순수 도메인 로직 (외부 의존 없음)
└── integration/
    └── api/
```

---

## 5. 아키텍처 — Clean Architecture + DDD

### 레이어 계층과 의존성 방향

각 Bounded Context 내부에서 레이어는 아래 방향으로만 참조합니다.

```
presentation  →  application  →  domain
                      ↑
               infrastructure
```

| 레이어 | 역할 | 외부 의존 |
|---|---|---|
| `domain` | 엔티티, VO, 레포지토리 인터페이스, 도메인 예외 | 없음 (순수 Python) |
| `application` | Use Case 조합, DTO | domain 인터페이스만 |
| `infrastructure` | ORM 모델, 레포지토리 구현체, 외부 API 어댑터 | SQLAlchemy, httpx 등 |
| `presentation` | FastAPI 라우터, 요청/응답 스키마 | application use case |

### Bounded Context

| Context | 책임 |
|---|---|
| `user` | 회원가입, 로그인, OAuth 연결, 2FA, 사용자 설정 |
| `todo` | 할 일 CRUD, 상태 전환, 날짜 배정 |
| `retrospective` | 회고 작성, AI 요약 트리거 |
| `notification` | 알림 생성, 읽음 처리 |
| `github` | GitHub 저장소 연결 (OAuth 토큰 재사용), 저장소 동기화, 커밋 조회, 회고 push, push target 설정 (`user_settings`에 통합) |

> GitHub API, Anthropic API는 도메인이 아닌 infrastructure 어댑터입니다. 별도 Bounded Context를 만들지 않습니다.

---

## 6. Domain Layer

### Entity 작성 규칙

```python
# app/todo/domain/models/todo.py
from dataclasses import dataclass
from datetime import datetime
from app.todo.domain.models.value_objects import TaskStatus
from app.todo.domain.exceptions.exceptions import AlreadyCompletedException

@dataclass
class Todo:
    id: str
    user_id: str
    title: str
    status: TaskStatus
    date_key: str               # "YYYY-MM-DD"
    created_at: datetime
    updated_at: datetime | None = None
    completed_at: datetime | None = None
    description: str = ""

    def complete(self) -> None:
        if self.status == TaskStatus.DONE:
            raise AlreadyCompletedException()
        self.status = TaskStatus.DONE
        self.completed_at = datetime.utcnow()

    def move_to(self, date_key: str) -> None:
        self.date_key = date_key
```

- Entity는 `dataclass`로 작성합니다.
- 상태 전환 로직과 불변식 검증은 entity 메서드에 작성합니다. 외부에서 필드를 직접 변경하지 않습니다.
- `id`는 `str` 타입으로 통일합니다.
- `updated_at`은 ORM이 자동 관리합니다. 도메인 로직에서 직접 수정하지 않습니다.

### Value Object 작성 규칙

```python
# app/todo/domain/models/value_objects.py
from enum import StrEnum

class TaskStatus(StrEnum):
    NOT_START = "not-start"
    IN_PROGRESS = "in-progress"
    DONE = "done"
```

- Value Object는 불변입니다 (`frozen=True` dataclass 또는 `StrEnum`).
- 비즈니스 유효성 검사 로직을 Value Object 안에 포함합니다.

### 도메인 예외

```python
# app/todo/domain/exceptions/exceptions.py
from app.shared.domain.exceptions.base import BaseAppException

class TodoNotFoundException(BaseAppException):
    code = "TODO_NOT_FOUND"

class AlreadyCompletedException(BaseAppException):
    code = "TODO_ALREADY_COMPLETED"
```

```python
# shared/domain/exceptions/base.py — 순수 Python, 외부 의존 없음
class BaseAppException(Exception):
    code: str = "INTERNAL_ERROR"

    def __init__(
        self,
        message: str = "",
        details: list[dict] | None = None,
    ) -> None:
        self.message = message
        self.details = details or []
        super().__init__(message)
```

- 도메인 예외는 `shared/domain/exceptions/base.py`의 `BaseAppException`을 상속합니다.
- `BaseAppException`은 순수 Python입니다. HTTP status code를 알지 못합니다.
- HTTP status 매핑은 `shared/infrastructure/errors/handler.py`에서 담당합니다.

### Repository Interface

```python
# app/todo/domain/repositories/repository.py
from abc import ABC, abstractmethod
from app.todo.domain.models.todo import Todo

class ITodoRepository(ABC):
    @abstractmethod
    async def save(self, todo: Todo) -> Todo: ...

    @abstractmethod
    async def find_by_id(self, id: str, user_id: str) -> Todo | None: ...

    @abstractmethod
    async def find_by_date_key(self, user_id: str, date_key: str) -> list[Todo]: ...

    @abstractmethod
    async def find_by_full_text(
        self, user_id: str, query: str, page: int, size: int
    ) -> tuple[list[Todo], int]: ...

    @abstractmethod
    async def delete(self, id: str, user_id: str) -> None: ...
```

- 인터페이스는 domain에 정의, 구현체는 infrastructure에 작성합니다.
- 메서드 시그니처는 도메인 엔티티를 반환합니다. ORM 모델을 반환하지 않습니다.
- 페이지네이션이 필요한 메서드는 `(items, total)` 튜플을 반환합니다.
- 연관 데이터 포함 여부는 메서드 이름에 명시합니다: `find_by_id_with_user()`.

### ID 생성

```python
# shared/domain/utils/id.py
import uuid

def generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"

# 결과: "todo_3f8a9c1b2d4e", "user_a1b2c3d4e5f6"
```

---

## 7. Application Layer

### Use Case 파일 규칙

**파일 1개 = 클래스 1개.** 예외 없이 적용합니다.

```
todo/application/use_cases/
├── create_todo.py         # CreateTodoUseCase
├── update_todo.py         # UpdateTodoUseCase
├── delete_todo.py         # DeleteTodoUseCase
├── complete_todo.py       # CompleteTodoUseCase
├── move_todo.py           # MoveTodoUseCase
└── get_todos_by_date.py   # GetTodosByDateUseCase
```

### Command / Query 분리

```python
# app/todo/application/dtos/commands.py
from dataclasses import dataclass

@dataclass(frozen=True)
class CreateTodoCommand:
    user_id: str
    title: str
    date_key: str
    description: str = ""
```

```python
# app/todo/application/dtos/queries.py
from dataclasses import dataclass

@dataclass(frozen=True)
class GetTodosByDateQuery:
    user_id: str
    date_key: str
```

### Use Case 구조

```python
# app/todo/application/use_cases/create_todo.py
from app.shared.domain.utils.id import generate_id
from app.todo.domain.repositories.repository import ITodoRepository
from app.notification.domain.repositories.repository import INotificationRepository
from app.todo.application.dtos.commands import CreateTodoCommand

class CreateTodoUseCase:
    def __init__(
        self,
        todo_repo: ITodoRepository,
        notification_repo: INotificationRepository,
    ) -> None:
        self._todo_repo = todo_repo
        self._notification_repo = notification_repo

    async def execute(self, cmd: CreateTodoCommand) -> Todo:
        todo = Todo(
            id=generate_id("todo"),
            user_id=cmd.user_id,
            title=cmd.title,
            status=TaskStatus.NOT_START,
            date_key=cmd.date_key,
            created_at=datetime.utcnow(),
            description=cmd.description,
        )
        saved = await self._todo_repo.save(todo)
        await self._notification_repo.save(
            Notification.create(user_id=cmd.user_id, message=f"'{cmd.title}' added")
        )
        return saved
```

- Use Case는 도메인 객체를 조합하고 repository를 호출합니다.
- infrastructure 구현체를 직접 import하지 않습니다. 인터페이스만 타입 힌트로 사용합니다.
- 트랜잭션은 dishka provider가 `factory.begin()`으로 관리합니다. Use Case는 명시적 commit/rollback을 호출하지 않습니다.

---

## 8. Infrastructure Layer

### SQLAlchemy ORM 모델

```python
# app/todo/infrastructure/persistence/models/todo_model.py
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column
from app.shared.infrastructure.database.base import Base

class TodoModel(Base):
    __tablename__ = "todos"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    title_tsv: Mapped[str] = mapped_column(TSVECTOR)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    date_key: Mapped[str] = mapped_column(String(10), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,   # UPDATE 시 자동 갱신
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_todos_title_tsv", "title_tsv", postgresql_using="gin"),
        Index("ix_todos_user_id_date_key", "user_id", "date_key"),
    )
```

- ORM 모델과 도메인 엔티티는 별개입니다. 상속하거나 직접 매핑하지 않습니다.
- Repository 구현체가 `TodoModel → Todo` 변환을 전담합니다.
- `updated_at`은 SQLAlchemy `onupdate`로 자동 갱신됩니다. 도메인에서 관리하지 않습니다.

### Repository 구현체 및 N+1 방지

```python
# app/todo/infrastructure/persistence/repositories/todo_repo.py
from sqlalchemy.orm import selectinload, joinedload

class TodoRepository(ITodoRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_date_key(self, user_id: str, date_key: str) -> list[Todo]:
        # 연관 데이터 불필요 — 로딩 없이 단순 조회
        result = await self._session.execute(
            select(TodoModel)
            .where(TodoModel.user_id == user_id, TodoModel.date_key == date_key)
        )
        return [self._to_entity(m) for m in result.scalars()]

    async def find_by_full_text(
        self, user_id: str, query: str, page: int, size: int
    ) -> tuple[list[Todo], int]:
        stmt = (
            select(TodoModel)
            .where(TodoModel.user_id == user_id)
            .where(TodoModel.title_tsv.match(query))
        )
        total = await self._session.scalar(
            select(func.count()).select_from(stmt.subquery())
        )
        result = await self._session.execute(
            stmt.offset((page - 1) * size).limit(size)
        )
        return [self._to_entity(m) for m in result.scalars()], total or 0

    def _to_model(self, entity: Todo) -> TodoModel: ...
    def _to_entity(self, model: TodoModel) -> Todo: ...
```

**N+1 방지 기준:**

| 상황 | 사용할 전략 |
|---|---|
| 단일 엔티티 + 연관 1건 | `joinedload` (JOIN 1회) |
| 목록 + 연관 다수 | `selectinload` (쿼리 2회, 메모리 효율적) |
| 연관 데이터 불필요 | 로딩 없이 단순 조회 |

연관 포함 메서드는 이름에 명시합니다.

```python
find_by_id(id)              # Todo만 반환
find_by_id_with_user(id)    # User 포함 반환 (joinedload)
```

---

## 9. Presentation Layer

### 라우터 구조

```python
# app/todo/presentation/router.py
from fastapi import APIRouter, Depends, status
from dishka.integrations.fastapi import FromDishka
from app.todo.application.use_cases.create_todo import CreateTodoUseCase
from app.todo.application.dtos.commands import CreateTodoCommand
from app.todo.presentation.requests.requests import TodoCreateRequest
from app.todo.presentation.responses.responses import TodoResponse
from app.shared.presentation.schemas.response import ApiResponse
from app.shared.infrastructure.auth.jwt import get_current_user
from app.shared.domain.context.user_context import UserContext

router = APIRouter(prefix="/todos", tags=["todos"])

@router.post("/", response_model=ApiResponse[TodoResponse], status_code=status.HTTP_201_CREATED)
async def create_todo(
    body: TodoCreateRequest,
    current_user: UserContext = Depends(get_current_user),
    use_case: FromDishka[CreateTodoUseCase],
) -> ApiResponse[TodoResponse]:
    todo = await use_case.execute(
        CreateTodoCommand(user_id=current_user.id, title=body.title, date_key=body.date_key)
    )
    return ApiResponse.created(TodoResponse.from_entity(todo))
```

- 라우터 함수는 요청 파싱 → Use Case 호출 → 응답 직렬화만 담당합니다.
- 인증은 `Depends(get_current_user)`, Use Case는 `FromDishka[...]`로 주입받습니다.

### CORS 설정

```python
# main.py
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,   # 환경변수로 관리
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 10. 의존성 주입 — dishka IoC Container

FastAPI의 `Depends` 중첩 문제를 해결하기 위해 **dishka**를 사용합니다.

### Scope 구분

| Scope | 수명 | 대상 |
|---|---|---|
| `Scope.APP` | 앱 전체 (Singleton) | GitHub 클라이언트, Anthropic 클라이언트, Redis, 설정 |
| `Scope.REQUEST` | 요청마다 생성/소멸 | DB 세션, Repository, Use Case |

### Provider 정의

```python
# shared/infrastructure/container/providers.py
from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

class AppProvider(Provider):
    scope = Scope.APP

    @provide
    def github_client(self, config: AppConfig) -> GitHubApiClient:
        return GitHubApiClient(token=config.github_token)

    @provide
    def anthropic_client(self, config: AppConfig) -> AnthropicApiClient:
        return AnthropicApiClient(api_key=config.anthropic_api_key)

    @provide
    def redis_cache(self, config: AppConfig) -> RedisCache:
        return RedisCache(url=config.redis_cache_url)


class RequestProvider(Provider):
    scope = Scope.REQUEST

    @provide
    async def db_session(
        self, factory: async_sessionmaker
    ) -> AsyncGenerator[AsyncSession, None]:
        async with factory.begin() as session:   # begin() = 성공 시 자동 커밋, 예외 시 자동 롤백
            yield session

    @provide
    def todo_repo(self, session: AsyncSession) -> ITodoRepository:
        return TodoRepository(session)

    @provide
    def notification_repo(self, session: AsyncSession) -> INotificationRepository:
        return NotificationRepository(session)

    @provide
    def create_todo_use_case(
        self,
        todo_repo: ITodoRepository,
        notification_repo: INotificationRepository,
    ) -> CreateTodoUseCase:
        return CreateTodoUseCase(todo_repo, notification_repo)
```

### 앱 초기화

```python
# main.py
from dishka import make_async_container
from dishka.integrations.fastapi import setup_dishka
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    container = make_async_container(AppProvider(), RequestProvider())
    setup_dishka(container, app=app)
    yield
    await container.close()   # Redis 커넥션 풀 등 리소스 정리

app = FastAPI(lifespan=lifespan)
```

### Celery 전용 컨테이너

Celery 태스크는 FastAPI request lifecycle 밖에서 실행되므로 dishka를 사용할 수 없습니다. 태스크 전용 컨테이너 빌더를 사용합니다.

```python
# shared/infrastructure/container/celery_container.py
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

def build_use_case_for_task(use_case_cls: type, **extra_deps):
    engine = create_async_engine(settings.db_url)
    session = AsyncSession(engine)

    repos = {
        "todo_repo": TodoRepository(session),
        "notification_repo": NotificationRepository(session),
        "anthropic_client": AnthropicApiClient(settings.anthropic_api_key),
        **extra_deps,
    }
    # use_case_cls의 생성자 파라미터에 맞춰 주입
    import inspect
    params = inspect.signature(use_case_cls.__init__).parameters
    kwargs = {k: v for k, v in repos.items() if k in params}
    return session, use_case_cls(**kwargs)
```

```python
# app/retrospective/infrastructure/tasks/summary_task.py
@celery_app.task(name="retrospective.generate_summary", ...)
def generate_summary_task(self, user_id: str, retro_id: str) -> dict:
    async def _run() -> dict:
        session, use_case = build_use_case_for_task(GenerateSummaryUseCase)
        async with session:
            return await use_case.execute(GenerateSummaryCommand(user_id, retro_id))

    return asyncio.run(_run())
```

### 테스트에서 오버라이드

```python
container = make_async_container(
    AppProvider(),
    RequestProvider(),
    MockAnthropicProvider(),   # 실제 API 호출 없이 Mock으로 교체
)
```

### 새 Use Case 등록 절차

1. `application/use_cases/`에 Use Case 클래스 작성 (파일 1개 = 클래스 1개)
2. `shared/infrastructure/container/providers.py`의 `RequestProvider`에 `@provide` 메서드 추가
3. 라우터에서 `FromDishka[NewUseCase]`로 주입

---

## 11. 에러 처리

### 에러 흐름

```
DomainException (shared/domain/exceptions/base.py 상속)
    ↓
Use Case에서 전파 (별도 변환 없이 그대로 올림)
    ↓
GlobalExceptionHandler (shared/infrastructure/errors/handler.py)
    ↓ HTTP 상태 코드는 handler의 STATUS_MAP에서 결정
HTTP Response { status, code, data, details }
```

### 에러 응답 형식

```json
{
    "status": "error",
    "code": "TODO_NOT_FOUND",
    "data": null,
    "details": [
        { "field": "todo_id", "message": "Todo with id 'todo_abc123' not found" }
    ]
}
```

- `code`: 프론트엔드가 번역 키로 사용하는 기계 판독 가능한 값
- `details[].message`: **개발자 디버그용 영어 메시지.** 사용자에게 직접 노출하지 않습니다. 프론트엔드는 `code`로 자체 i18n 처리합니다.

### GlobalExceptionHandler

```python
# shared/infrastructure/errors/handler.py
from app.shared.infrastructure.errors.codes import ErrorCode

STATUS_MAP: dict[str, int] = {
    ErrorCode.TODO_NOT_FOUND: 404,
    ErrorCode.USER_NOT_FOUND: 404,
    ErrorCode.TODO_ALREADY_COMPLETED: 409,
    ErrorCode.USER_EMAIL_DUPLICATED: 409,
    ErrorCode.AUTH_TOKEN_EXPIRED: 401,
    ErrorCode.AUTH_TOKEN_INVALID: 401,
}

async def app_exception_handler(request: Request, exc: BaseAppException) -> JSONResponse:
    status_code = STATUS_MAP.get(exc.code, 500)
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "error",
            "code": exc.code,
            "data": None,
            "details": [{"field": d["field"], "message": d["message"]} for d in exc.details],
        },
    )
```

### 에러 코드 네이밍

`{DOMAIN}_{NOUN}_{STATE}` 형식을 따릅니다.

```python
# shared/infrastructure/errors/codes.py
class ErrorCode:
    # User
    USER_NOT_FOUND = "USER_NOT_FOUND"
    USER_EMAIL_DUPLICATED = "USER_EMAIL_DUPLICATED"
    # Auth
    AUTH_TOKEN_EXPIRED = "AUTH_TOKEN_EXPIRED"
    AUTH_TOKEN_INVALID = "AUTH_TOKEN_INVALID"
    AUTH_2FA_CODE_INVALID = "AUTH_2FA_CODE_INVALID"
    # Todo
    TODO_NOT_FOUND = "TODO_NOT_FOUND"
    TODO_ALREADY_COMPLETED = "TODO_ALREADY_COMPLETED"
    # Retrospective
    RETRO_NOT_FOUND = "RETRO_NOT_FOUND"
    RETRO_SUMMARY_ALREADY_IN_PROGRESS = "RETRO_SUMMARY_ALREADY_IN_PROGRESS"
```

### Validation 에러 (422)

FastAPI의 `RequestValidationError`도 동일 형식으로 오버라이드합니다.

```json
{
    "status": "error",
    "code": "VALIDATION_ERROR",
    "data": null,
    "details": [
        { "field": "title", "message": "Field required" }
    ]
}
```

---

## 12. API 응답 형식

### 공통 응답 래퍼

```python
# shared/presentation/schemas/response.py
from pydantic import BaseModel, Field
from typing import Generic, TypeVar

T = TypeVar("T")

class ApiResponse(BaseModel, Generic[T]):
    status: str
    code: str
    data: T | None

    @classmethod
    def ok(cls, data: T) -> "ApiResponse[T]":
        return cls(status="success", code="OK", data=data)

    @classmethod
    def created(cls, data: T) -> "ApiResponse[T]":
        return cls(status="success", code="CREATED", data=data)


class PaginatedData(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int


class PaginationQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=100)   # 최대 100
```

### 단건 응답

```json
{
    "status": "success",
    "code": "OK",
    "data": { "id": "todo_abc123", "title": "회고 작성하기" }
}
```

### 페이지네이션 응답

페이지네이션은 1-indexed(`page=1`이 첫 페이지)입니다.

```json
{
    "status": "success",
    "code": "OK",
    "data": {
        "items": [ ... ],
        "total": 42,
        "page": 1,
        "size": 20
    }
}
```

---

## 13. 크로스 도메인 참조 규칙

순환 참조(Circular Import) 방지를 위해 레이어별로 아래 규칙을 적용합니다.

| 레이어 | 타 도메인 엔티티/VO | 타 도메인 Repository 인터페이스 | 타 도메인 Use Case |
|---|---|---|---|
| Domain | ❌ 금지 | ❌ 금지 | ❌ 금지 |
| Application | ❌ 금지 | ✅ 허용 | ❌ 금지 |
| Infrastructure | ❌ 금지 | ❌ 금지 | ❌ 금지 |
| Presentation | ❌ 금지 | ❌ 금지 | ❌ 금지 |

```python
# 금지 — todo 도메인 내부에서 user 엔티티 직접 import
from app.user.domain.models.user import User          # ❌

# 허용 — shared의 공통 타입(ID, VO)만 참조
from app.shared.domain.models.base import UserId      # ✅

# 허용 — Application Layer에서 타 도메인 Repository 인터페이스 참조
from app.notification.domain.repositories.repository import INotificationRepository  # ✅
```

### shared/domain/models/base.py에 두는 것들

- `BaseEntity` (공통 필드: `id`, `created_at`, `updated_at`)
- 도메인 간 공유 ID 타입: `UserId`, `TodoId`, `RetroId`
- 여러 도메인이 공통으로 쓰는 VO: `DateKey`, `Email`

---

## 14. 스키마 설계 규칙

### 원칙

- 스키마는 엔드포인트 간에 직접 공유하지 않습니다.
- 공통 필드(`id`, `created_at` 등)는 `shared/`의 `BasePydanticModel` 상속으로 처리합니다.
- 도메인 엔티티 → 응답 스키마 변환은 `from_entity()` classmethod를 사용합니다.

```python
# 금지 — 다른 도메인 스키마를 조합으로 재사용
class TodoResponse(BaseModel):
    assigned_user: UserResponse    # ❌

# 허용 — 필요한 필드만 인라인으로 선언
class TodoResponse(BaseModel):
    assigned_user_id: str          # ✅
    assigned_user_name: str        # ✅
```

### from_entity 패턴

```python
# app/todo/presentation/responses/responses.py
class TodoResponse(BaseModel):
    id: str
    title: str
    status: str
    date_key: str
    created_at: datetime

    @classmethod
    def from_entity(cls, todo: Todo) -> "TodoResponse":
        return cls(
            id=todo.id,
            title=todo.title,
            status=todo.status.value,
            date_key=todo.date_key,
            created_at=todo.created_at,
        )
```

---

## 15. Async / Sync 규칙

FastAPI의 이벤트 루프 블로킹을 방지하는 3가지 하드 룰입니다.

### 룰 1 — 외부 HTTP 호출은 httpx async만 사용

```python
# 금지
import requests
response = requests.get(...)    # ❌ 이벤트 루프 블로킹

# 허용
import httpx
async with httpx.AsyncClient() as client:
    response = await client.get(...)    # ✅
```

### 룰 2 — CPU 집약 / 지연이 긴 작업은 Celery로

```python
# 금지 — async 라우터에서 직접 장시간 작업
async def generate_summary():
    result = anthropic.messages.create(...)    # ❌

# 허용 — Celery 태스크로 위임 후 즉시 반환
async def generate_summary():
    generate_summary_task.delay(retro_id)      # ✅
    return ApiResponse.ok({"message": "Summary generation started"})
```

### 룰 3 — 불가피한 sync 라이브러리는 run_in_executor

```python
# asyncio.get_running_loop() 사용 (Python 3.10+ deprecated된 get_event_loop() 사용 금지)
loop = asyncio.get_running_loop()
result = await loop.run_in_executor(None, sync_blocking_function, arg1, arg2)
```

---

## 16. 데이터베이스

### 전문 검색 (tsvector)

검색이 필요한 컬럼은 초기 스키마부터 tsvector 컬럼과 GIN 인덱스를 포함합니다.

| 테이블 | tsvector 컬럼 | 대상 컬럼 |
|---|---|---|
| `todos` | `title_tsv` | `title` |
| `journal_entries` | `content_tsv` | `title + content` |

tsvector는 PostgreSQL 트리거로 자동 갱신합니다. `'simple'` 설정은 한국어를 포함한 다국어에 적합합니다 (어간 처리 없이 토큰 분리).

```sql
CREATE OR REPLACE FUNCTION update_todo_tsv() RETURNS trigger AS $$
BEGIN
  NEW.title_tsv := to_tsvector('simple', NEW.title);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER todo_tsv_update
  BEFORE INSERT OR UPDATE ON todos
  FOR EACH ROW EXECUTE FUNCTION update_todo_tsv();
```

트리거 생성 SQL은 Alembic 마이그레이션의 `upgrade()`에 `op.execute()`로 포함합니다.

### Alembic async 설정

async SQLAlchemy를 사용하려면 기본 `env.py`를 아래 패턴으로 수정해야 합니다.

```python
# migrations/env.py
import asyncio
from sqlalchemy.ext.asyncio import async_engine_from_config

def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
    )

    async def run_async_migrations() -> None:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)

    asyncio.run(run_async_migrations())
```

### 마이그레이션 규칙

- 마이그레이션 파일은 `--autogenerate`로 생성합니다.
- 트리거 등 자동 감지 불가 DDL은 수동으로 `op.execute()` 추가 후 주석으로 이유를 명시합니다.
- `downgrade()` 함수는 항상 작성합니다.

### 테이블 네이밍

- 테이블명: 복수형 snake_case (`todos`, `journal_entries`, `users`)
- 컬럼명: snake_case
- FK 컬럼: `{참조테이블_단수}_{참조컬럼}` (`user_id`, `todo_id`)
- 인덱스명: `ix_{테이블}_{컬럼}` (`ix_todos_user_id`)

---

## 17. Redis 역할 분담

| DB 번호 | 용도 | 사용 위치 |
|---|---|---|
| `redis://redis:6379/0` | Celery 브로커 (태스크 큐) | `celery_app.broker_url` |
| `redis://redis:6379/1` | Celery result backend | `celery_app.result_backend` |
| `redis://redis:6379/2` | 앱 캐시 (OAuth state / onboarding / password reset / email verify) | `REDIS_CACHE_URL` |
| `redis://redis:6379/3` | Auth 세션 (refresh token 세션 레코드 + 역인덱스) | `REDIS_AUTH_URL` |

캐시 키 네이밍 + TTL (TTL 은 모두 `.env` 에서 관리):

```
# DB 2 — 앱 캐시
auth:oauth:state:{state}                    # TTL: OAUTH_STATE_TTL_SECONDS
auth:onboarding:{token}                     # TTL: ONBOARDING_TOKEN_TTL_SECONDS
auth:pwreset:{token}                        # TTL: PASSWORD_RESET_TTL_SECONDS
auth:pwreset:cooldown:{email}               # TTL: PASSWORD_RESET_COOLDOWN_TTL_SECONDS
auth:email:code:{email}                     # TTL: EMAIL_VERIFY_CODE_TTL_SECONDS
auth:email:cooldown:{email}                 # TTL: EMAIL_COOLDOWN_TTL_SECONDS
auth:email:verified:{email}                 # TTL: EMAIL_VERIFIED_TTL_SECONDS

# DB 3 — 세션 (§18 Session 보안 정책 참조)
auth:session:{sessionId}                    # TTL: REFRESH_TOKEN_EXPIRE_DAYS * 86400
auth:user_sessions:{user_id}                # Set, TTL 동일
```

---

## 18. 인증 / 인가

### 인증 흐름

| 방식 | 흐름 |
|---|---|
| 이메일/패스워드 | `POST /auth/register` 또는 `POST /auth/login` → access token(body) + refresh cookie 발급 |
| GitHub OAuth | `GET /auth/oauth/github/authorize` → GitHub → `GET /auth/oauth/github/callback` → postMessage + cookie |
| Google OAuth | `GET /auth/oauth/google/authorize` → Google → `GET /auth/oauth/google/callback` → postMessage + cookie |
| OAuth 신규 사용자 | callback → onboarding cookie + `oauth_onboarding_required` postMessage → `POST /auth/oauth/onboarding` 으로 가입 완료 |
| OAuth 계정 link | `POST /auth/oauth/{provider}/link/init` (Bearer) → 응답 `authorizeUrl` 을 popup 으로 open |

> **2FA(TOTP) 는 현재 비활성화 상태**입니다. 관련 컬럼은 migration 007 에서 제거됐고, pre_auth 토큰 흐름도 없습니다.

### 토큰 구조

```python
# Access Token (JWT, stateless) — 유효기간: settings.auth.access_token_expire_minutes (기본 15분)
{ "sub": "user_id", "type": "access", "exp": ... }

# Refresh Token (opaque, NOT a JWT) — 유효기간: settings.auth.refresh_token_expire_days (기본 7일)
# 형식: "{sessionId}.{secret}"  예) "sess_abc123def....xyz.k4Hf...32B"
#   - sessionId: opaque random — Redis session 레코드의 키
#   - secret:    Redis 에는 SHA-256 hash 로만 저장
# 클라이언트 측: HttpOnly Secure SameSite=Lax 쿠키. JS 접근 불가.
```

상세 검증·rotation·reuse detection 정책은 본 §18 의 **Session 보안 정책** 섹션 참조.

### 라우터 보호

```python
# 일반 인증 — Bearer access token
current_user: UserContext = Depends(get_current_user)

# Refresh token 쿠키 추출 (refresh / logout / 세션 관리 라우트용)
raw_refresh: str = Depends(extract_refresh_token)
```

### OAuth state 보안

```python
import secrets

# 생성 — 암호학적으로 안전한 랜덤 값
state = secrets.token_urlsafe(32)

# Redis 저장 — TTL = OAUTH_STATE_TTL_SECONDS (기본 600s = 10분), 콜백 후 즉시 삭제 (1회용)
await redis.setex(f"user:oauth_state:{state}", settings.auth.oauth_state_ttl_seconds, user_session_id)

# 콜백 검증 — getdel로 읽는 동시에 삭제 (재사용 방지)
stored = await redis.getdel(f"user:oauth_state:{state}")
if not stored:
    raise OAuthStateInvalidException()
```

### OAuth 계정 link 흐름 (이미 로그인된 사용자가 provider 추가 연결)

이메일 가입 사용자(또는 Google 사용자)가 자신의 계정에 GitHub 등 다른 provider를 추가 연결하려는 케이스. 기존 callback은 email 매칭으로 자동 연결을 시도하지만, **이메일이 다른 경우 새 사용자가 잘못 생성되는 위험**이 있어 별도 진입점을 둡니다.

**POST init 패턴** 사용 — popup GET 으로는 Bearer 헤더 전송이 불가능하므로, FE 가 먼저 인증된 POST 호출로 authorize URL 을 받아 popup 으로 직접 엽니다.

```
1. POST /auth/oauth/{provider}/link/init         (Bearer 인증 필수)
   ├─ state_cache.create_link_state(provider, current_user.id)
   │    → Redis: auth:oauth:state:{state} = {"provider":..., "link_user_id":...}
   └─ 200 { "authorizeUrl": "https://github.com/login/oauth/authorize?..." }

2. FE: window.open(authorizeUrl)  → GitHub 동의 화면

3. provider redirect → GET /auth/oauth/{provider}/callback?code=...&state=...
   ├─ state_cache.consume_state(state) → {provider, link_user_id}
   ├─ link_user_id 있음 → link 분기
   │   ├─ provider 계정이 다른 사용자에 이미 연결 → 409 AUTH_OAUTH_ACCOUNT_ALREADY_LINKED
   │   ├─ 현재 사용자가 같은 provider에 다른 계정 연결 → 409 AUTH_OAUTH_PROVIDER_ALREADY_LINKED
   │   ├─ 동일 provider account 재요청 → 멱등(access_token만 갱신)
   │   └─ 신규 → OAuthConnection 저장
   └─ HTML postMessage { type: "oauth_linked", provider }
```

**설계 결정**:
- 기존 `/auth/oauth/{provider}/authorize` 는 익명 GET — Bearer 헤더 없음
- popup GET 으로 Bearer 헤더는 못 실음 → init 단계를 POST 로 분리해 표준 Authorization 헤더 사용
- callback 한 곳에 흐름을 묶고 state 페이로드로 분기 → callback URL 추가 없이 단일 진입점 유지
- link 결과는 새 토큰을 발급하지 않음 (이미 로그인된 세션 그대로 사용)
- **OAuth callback URL 은 FE proxy origin 으로 통일** (`http://{fe-origin}/api/v1/auth/oauth/{provider}/callback`). 그래야 callback HTML 의 `window.opener.postMessage` 가 FE origin 으로 도달.

### 비밀번호 재설정 흐름

```
1. POST /auth/password/reset/request { email }
   ├─ 항상 200 (이메일 enumeration 방지)
   ├─ 내부 분기: 미가입 / OAuth 전용 / 쿨다운(PASSWORD_RESET_COOLDOWN_TTL_SECONDS) → silent skip
   ├─ 정상 → token = secrets.token_urlsafe(32)
   │        Redis: auth:pwreset:{token} = user_id  TTL=PASSWORD_RESET_TTL_SECONDS
   └─ 이메일 발송 (Apple 다크모드 템플릿 + plain text — 본문의 "X분 유효"도 동일 값에서 derive)

2. POST /auth/password/reset/confirm { token, newPassword, newPasswordConfirm }
   ├─ Redis getdel(auth:pwreset:{token}) → user_id (1회용)
   ├─ user.password_hash 검증 (OAuth 전용 → 400 AUTH_PASSWORD_RESET_NOT_ALLOWED)
   ├─ password_hash = hash_password(newPassword)
   └─ session_service.revoke_all(user_id)   # 모든 세션 폐기 → 모든 기기 강제 로그아웃
```

**보안 결정**:
- 토큰은 Redis 1회용. 사용 후 즉시 삭제
- 성공 시 모든 세션 폐기 → 비밀번호 노출 가정 하에 다른 기기 보호
- 응답에서 이메일 등록 여부 누설 금지

### Session 보안 정책 — server-side trust anchor + RT rotation + reuse detection

OAuth 2.1 best practice 준수. Access token 은 stateless JWT 로 평상시 부하를 낮게 유지하고, refresh 길목에서만 Redis 의 세션 레코드를 신뢰 기준점으로 다중 검증.

#### Refresh Token 형식
```
RT = "{sessionId}.{secret}"
   = "sess_<uuid7_hex>.<urlsafe_32B>"
```
- sessionId 는 opaque random — 클라이언트 추측 불가
- secret 은 서버 측에서 SHA-256 hash 로만 저장 (Redis 유출 시에도 RT 원문 노출 X)
- RT 자체는 클라이언트 측 HttpOnly Secure SameSite=Lax 쿠키

#### Redis 스키마
```
KEY  auth:session:{sessionId}          JSON  → SessionRecord
KEY  auth:user_sessions:{user_id}      Set   → {sessionId, ...}
TTL  refresh_token_expire_days * 86400

SessionRecord = {
  user_id, rt_hash, prev_rt_hash, prev_at,
  device_info, device_label, ip_prefix,
  issued_at, last_used_at, rotation_counter
}
```

#### Refresh 정책 (`SessionService.rotate`)
```
1. RT split → sessionId, secret. presented_hash = SHA-256(secret)
2. Redis 세션 조회 → 없으면 401 AUTH_REFRESH_TOKEN_INVALID
3. 매칭 분기:
   a) presented_hash == rt_hash         → 정상 rotation
      - 새 secret 발급, rt_hash 교체, prev_rt_hash 백업, rotation_counter++
   b) presented_hash == prev_rt_hash AND now - prev_at < SESSION_GRACE_WINDOW_SECONDS → grace hit
      - 동시 refresh race (탭 2개) — 새 RT 발급하지 않음, 기존 쿠키 유지
      - structlog: session.refresh_grace_hit
   c) 그 외                              → 탈취 의심
      - cache.delete_all(user_id) 로 해당 user 모든 세션 즉시 폐기
      - structlog WARNING: session.refresh_reuse_detected
        (presented_hash, current_hash, prev_hash, prev_at, purged_session_ids,
         ip_prefix, device_label, user_agent)
      - 401 AUTH_REFRESH_TOKEN_REUSE_DETECTED
```

#### 세션 관리 API (사용자 자가 통제)
```
GET    /auth/sessions                  # 활성 세션 목록 (is_current 표시)
DELETE /auth/sessions/{sessionId}      # 단일 세션 폐기
DELETE /auth/sessions                  # 현재 외 전부 폐기 (revoked_count 반환)
```

#### 무효화 경로 (모두 Redis 키 삭제 1동작으로 일원화)
| 행위 | 호출 |
|---|---|
| 로그아웃 | `session_service.revoke(sessionId, user_id)` |
| 비밀번호 재설정 완료 | `session_service.revoke_all(user_id)` |
| 탈취 탐지 | `_handle_reuse` 내부에서 `cache.delete_all` |
| 다른 기기 전부 로그아웃 | `session_service.revoke_others(user_id, current_sid)` |

#### 보안 감사 로깅
별도 `security` 채널 (`shared/infrastructure/logger/security.py`) — structlog JSONRenderer 로 stdout 에 출력. 운영에서는 별도 sink (SIEM, audit table) 로 라우팅 가능.
- `session.refresh_grace_hit` INFO — race detection
- `session.refresh_reuse_detected` WARNING — 탈취 의심 (전체 컨텍스트 포함)
- `session.revoked` / `session.revoked_all` / `session.revoked_others` INFO

### 국가 변경 이력 (user_country_history)

통계/분석 용도의 audit log. 사용자별 country/region/timezone 변경 시점을 보존.

```
user_country_history
├ id          (uch_*)
├ user_id     FK users(id) ON DELETE CASCADE
├ country     CHAR(2)      -- ISO 3166-1 alpha-2
├ region      VARCHAR(8)   -- (deprecated) 과거 ISO 3166-2. 신규 입력은 NULL
├ timezone    VARCHAR(64)  -- IANA tz at change time
├ source      VARCHAR(32)  -- 'registration' | 'oauth_onboarding' | 'settings_update'
└ created_at  TIMESTAMPTZ
```

**기록 지점** (3곳):
- `RegisterUseCase` → `source=registration`
- `CompleteOnboardingUseCase` → `source=oauth_onboarding`
- `UpdateCountryUseCase` → `source=settings_update` (실제 값이 변경된 경우만, 동일 값 재전송은 무시)

**Backfill**: migration 011 이 기존 모든 유저에 대해 현재 country 로 `source=registration` 1행을 삽입.

**인덱스** (분석 쿼리용):
- `ix_uch_user_id_created_at` (user_id, created_at DESC) — 특정 유저 시계열
- `ix_uch_country_created_at` (country, created_at DESC) — 국가별 코호트
- `ix_uch_created_at` (created_at) — 전체 변경 빈도

### OAuth 신규 사용자 온보딩 흐름 (국가 정보 수집)

OAuth 콜백에서 처음 보이는 사용자는 곧바로 계정을 만들지 않고 **임시 onboarding token** 을 발급해 FE 가 국가/timezone 을 입력하도록 유도합니다.

```
1. /auth/oauth/{provider}/callback
   ├─ provider 토큰 교환 + user_info 조회
   ├─ 분기:
   │   • 기존 사용자       → 일반 access/refresh 발급
   │   • 신규 사용자       → Redis에 onboarding payload 저장 (TTL=ONBOARDING_TOKEN_TTL_SECONDS)
   │                       → HttpOnly Cookie `onboarding_token` 발급
   │                       → postMessage({ type: "oauth_onboarding_required" })
2. POST /auth/oauth/onboarding
   ├─ Cookie의 onboarding_token으로 Redis 조회 (consume)
   ├─ body { country, timezone? }  validation
   ├─ resolve_timezone(country, timezone) → IANA tz 결정
   ├─ User + OAuthConnection 생성
   └─ refresh_token Cookie + access_token body
```

Redis 키 형식: `auth:onboarding:{token} → JSON {provider, provider_user_id, email}`.

### 사용자 타임존 & 국가

| 필드 | 의미 | 변경 API |
|---|---|---|
| `users.country` | ISO 3166-1 alpha-2 (`KR`, `US`, ...). pycountry 기준 전 249개국 | `PATCH /settings/country` (timezone 자동/명시) |
| `users.region` | **(deprecated)** 과거 ISO 3166-2. 신규 입력 받지 않음. 신규 row 는 NULL | — |
| `users.timezone` | IANA tz (`Asia/Seoul`, `America/Los_Angeles`). AI 요약 스케줄링 기준 | `PATCH /settings/timezone` (단독 override) |

#### 국가 → IANA timezone 결정 흐름

```
1. 국가 코드 검증
   is_supported_country(country) → ISO 3166-1 alpha-2 등록 여부 (pycountry)

2. 옵션 조회
   country_timezone_options(country) → pytz.country_timezones[country]
                                       (CLDR-derived, OS tzdata 자동 추적)

3. 결정
   if len(options) == 1:
       timezone = options[0]   # 자동 결정 — FE 에서 timezone 생략 가능
   else:
       if not timezone:
           raise AUTH_COUNTRY_TIMEZONE_REQUIRED
       if timezone not in options:
           raise AUTH_TIMEZONE_INVALID
       # OK
```

#### FE 가 timezone 옵션 받는 법
`GET /settings/countries/{code}/timezones` → `{ country, timezones[], multi }`
- `multi: false` → FE 는 timezone 입력란을 숨겨도 됨
- `multi: true`  → FE 는 `timezones[]` 로 드롭다운 채움

#### 데이터 소스 & 갱신 정책
- **국가 목록**: `pycountry` (ISO 3166-1, 249개). 신규 국가 발생 시 라이브러리 업데이트로 자동 반영.
- **국가 → tz 매핑**: `pytz.country_timezones` (CLDR). DST 정책 변경, tz 신설·통합도 라이브러리 + OS tzdata 업데이트로 자동 반영. **dict 하드코딩 없음** — 코드 수정·배포 불필요.

AI 자동 요약은 **사용자 tz 기준 새벽 1시** 에 트리거.

### GitHub commits 조회 (`GET /github/commits`)

회고 작성 화면이 사용자의 그 날 commit 을 끌어다 보여주는 핵심 경로.

#### 흐름 (`GetCommitsByDateUseCase`)
```
1. user 조회 → user.timezone 추출
2. target_date 결정 (없으면 user tz 기준 오늘)
3. 사용자 tz 의 [00:00, 24:00) → UTC ISO 변환 (since/until)
4. GitHub credentials 획득 (access_token + login + verified_emails)
   - oauth_connections.provider_login / provider_verified_emails 캐시 우선
   - 둘 중 하나라도 없으면 /user 또는 /user/emails 호출 → DB backfill (lazy)
5. commit_read_enabled=true 저장소 N개 → asyncio.gather 로 병렬 list_commits
   - `?author=` 필터 사용하지 않음 — 그 repo 의 모든 commit 을 받음
6. 각 commit 에 대해 _is_user_commit 으로 본인 매칭 판정 (login OR verified email)
7. 결과 분류:
   - 성공: 매칭된 commit 만 누적
   - GitHubRepositoryNotFoundException: failedRepositories[reason="not_found"]
   - 기타 예외: failedRepositories[reason="unknown"] + structlog warning
   - GitHubTokenInvalid / RateLimited / ApiUnavailable: 전체 raise (한 repo 만 발생해도)
8. commits 시간 내림차순 정렬 → CommitsByDateResult 반환
```

#### 정책 결정
- **public repo only**: OAuth scope 가 `user:email,public_repo` 라 private repo 는 link 자체가 안 됨. 어쩌다 등록돼도 404 → `failedRepositories` 로 사용자에게 노출.
- **silent skip 금지**: 옛 구현은 단일 repo 실패를 조용히 무시했으나, 신정책은 응답에 `failedRepositories` 로 노출하고 백엔드에도 `github.commits.*` 채널로 warning 로깅.
- **fatal vs per-repo 구분**: 토큰/제한/외부 가용성 문제는 사용자 전체 흐름 차단(전체 raise) 이 더 유익. 저장소 단위 문제는 다른 결과 보존.
- **login + verified emails 캐싱**: `oauth_connections.provider_login` (migration 012) + `provider_verified_emails` (migration 014) 에 저장. callback/link/onboarding 시 자동 저장. 구 데이터는 첫 commits 호출 시 lazy backfill.

#### 본인 commit 매칭 정책 (Phase 1 — migration 014)

**문제**: 이전 정책은 GitHub `?author=<login>` 쿼리 필터를 사용했다. GitHub 는 commit author email 이 그 GitHub 계정에 verified 등록돼 있을 때만 매칭하므로, gitbash 등 로컬 `git config user.email` 이 GitHub 에 등록 안 됐으면 본인이 push 한 commit 도 0건 반환.

**해결**: `?author=` 필터를 빼고 모든 commit 을 받은 뒤 서버사이드 OR 필터.

`get_commits_by_date.py:_is_user_commit`:
```
match = (
    commit.author.login == creds.login
    OR commit.committer.login == creds.login
    OR commit.author.email ∈ creds.verified_emails
    OR commit.committer.email ∈ creds.verified_emails
)
```

`verified_emails` 는 `/user/emails` 응답 중 `verified=true` 만. OAuth scope 에 `user:email` 포함. 사용자가 gitbash 의 `git config user.email` 을 GitHub Settings → Emails 에 verified 로 등록만 해두면 자동으로 본인 commit 으로 잡힌다.

**노출 신호**: `GET /github/connection` 응답의 `hasVerifiedEmails: bool` 로 FE 가 verified emails 보유 여부 확인. false 면 사용자에게 GitHub 재연결 또는 emails 등록 안내.

#### 빈 access_token 처리 (P3 — OAuth 신규 사용자)
OAuth 온보딩 직후 사용자는 `oauth_connections.access_token=""` 상태일 수 있다. `_token.py:get_github_access_token` 이 빈 토큰을 `None` 과 동등하게 취급 → `GITHUB_CONNECTION_NOT_FOUND` (400). FE 는 "GitHub 다시 연결" 안내 후 `POST /auth/oauth/github/link/init` 흐름으로 유도.

### GitHubApiClient — httpx 풀링

`GitHubApiClient` 는 APP scope 단일 인스턴스로 `httpx.AsyncClient` 를 멤버 보유. 메서드마다 `async with httpx.AsyncClient()` 를 새로 만들지 않아 커넥션 풀 재사용. 종료 시 `main.py` 의 lifespan 에서 `await api_client.close()` 호출.

### 회고록 GitHub push 상태 (retrospective_pushes)

`POST /github/retrospectives/push` 성공 시 백엔드가 push 레코드를 영속화. 이후 `GET /entries(/{id})`, `GET /summaries(/{id})` 응답에 `githubPush` 필드로 노출.

#### 데이터 모델
```
retrospective_pushes
├ id                     (rp_*)
├ user_id                FK users(id) ON DELETE CASCADE
├ period_type            VARCHAR(16)   -- 'daily' | 'weekly' | 'monthly' | 'annual'
├ period_key             VARCHAR(32)   -- 'YYYY-MM-DD' | 'YYYY-MM-WN' | 'YYYY-MM' | 'YYYY'
├ repository_id          TEXT          -- 백엔드 github_repositories.id
├ repository_full_name   VARCHAR(255)  -- denormalized (repo unlink 후에도 표시)
├ path                   VARCHAR(512)
├ commit_sha             VARCHAR(64)
├ html_url               TEXT
├ pushed_at              TIMESTAMPTZ
├ created_at / updated_at
└ UNIQUE (user_id, period_type, period_key)
```
인덱스: `ix_retro_pushes_user_pushed_at (user_id, pushed_at)` — 향후 "내 push 이력" 화면용.

#### 키 단위는 period — entity 가 아님 (의도된 모델)
GitHub 측 파일은 `{period_folder}/{period_key}.md` 단일이므로, push 상태도 1:1로 (user, period_type, period_key) 단위로만 의미가 있다. 같은 주에 JournalEntry(weekly) 와 RetroSummary(weekly) 가 함께 있으면 **둘 다 같은 push 레코드를 가리킨다** — 이는 거짓이 아니라 진실(파일이 하나) 의 반영.

#### 매핑 헬퍼 — `app.github.domain.utils.period_mapping`
```python
entry_to_period(entry) -> (period_type, period_key)
summary_to_period(summary) -> (period_type, period_key)
```
- `RetroType.YEARLY` → `'annual'` 로 정규화 (push API 명명과 일치).
- weekly 는 `shared.domain.utils.period.week_of_month` 사용 (majority-day 방식).

#### Enrich 흐름 (라우터)
```
1. use_case.execute(...) → entries / summaries
2. keys = [entry_to_period(e) for e in entries]
3. pushes = push_repo.find_many(user_id, keys)   # 한 번의 batch SELECT
4. push_map = {(p.period_type, p.period_key): p for p in pushes}
5. responses 빌드 시 push_map.get((pt, pk)) 주입
```
N+1 없음 — 항상 한 번의 batch query.

#### `githubPush` 응답 필드
```json
{
  "pushedAt": "...",
  "commitSha": "...",
  "htmlUrl": "...",
  "path": "daily/2026-06-08.md",
  "repositoryFullName": "owner/archive"
}
```
미푸시면 `null`.

---

## 19. Celery Worker

### 태스크 위치

도메인에 귀속되는 태스크는 해당 도메인의 `infrastructure/tasks/`에 작성합니다.

```
app/retrospective/infrastructure/tasks/summary_task.py
```

Celery 앱 인스턴스와 Beat 스케줄은 `shared/infrastructure/worker/celery_app.py`에서 관리합니다.

### 태스크 작성 규칙

```python
# app/retrospective/infrastructure/tasks/summary_task.py
import asyncio
from app.shared.infrastructure.worker.celery_app import celery_app
from app.shared.infrastructure.container.celery_container import build_use_case_for_task

@celery_app.task(
    name="retrospective.generate_summary",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def generate_summary_task(self, user_id: str, retro_id: str) -> dict:
    async def _run() -> dict:
        session, use_case = build_use_case_for_task(GenerateSummaryUseCase)
        async with session:
            return await use_case.execute(GenerateSummaryCommand(user_id, retro_id))

    try:
        return asyncio.run(_run())
    except Exception as exc:
        raise self.retry(exc=exc)
```

- 태스크명: `{도메인}.{동작}` 형식
- `max_retries`, `default_retry_delay`를 항상 명시합니다.
- 태스크는 진입점 역할만 합니다. 비즈니스 로직은 Use Case에 위임합니다.

### Beat 스케줄 — 사용자 tz 기반 자동 요약

Celery beat은 매시간 정각 단일 dispatcher 태스크만 발사합니다. dispatcher가 각 사용자의 `users.timezone` 기준 "현지 1am" 도달 여부를 판단해 fan-out합니다.

```python
# app/worker/celery_app.py
celery_app.conf.beat_schedule = {
    "dispatch-summaries-hourly": {
        "task": "worker.dispatch_summaries_for_tz",
        "schedule": crontab(minute=0),  # 매시간 정각
    },
}
```

**왜 단일 dispatcher인가?**
- Celery beat은 단일 tz 가정으로 동작 (UTC). 사용자별 다른 tz를 직접 지원하지 않음.
- Hourly tick + 사용자 tz 비교가 코드/운영 비용 면에서 가장 단순.

**dispatcher 흐름** (`app/worker/tasks/dispatch_summaries_for_tz.py`):

1. `user_settings`에서 `auto_summary_* = true` 사용자 + `users.timezone` JOIN 조회
2. 각 사용자에 대해 `now_utc.astimezone(ZoneInfo(user.tz)).hour == 1` 검사
3. `last_summary_date_local`와 현재 현지 날짜가 같으면 skip (DST fall-back 중복 방지)
4. 현지 날짜로 schedule type 결정 (1/1 → annual, 매월 1일 → monthly, 월요일 → weekly)
5. `auto_summary_*` 플래그와 schedule type 매칭 확인
6. fan-out 시 사용자별 결정적 지터 적용 — `countdown = hash(user_id) % SUMMARY_JITTER_SECONDS`
7. `last_summary_date_local` 갱신

**환경 변수**:
- `SUMMARY_JITTER_SECONDS` (기본 1800) — 0이면 정시, 1800이면 0~30분 분산, 3600이면 0~60분 분산

**기간 계산**:
- 주차 산정은 majority-day 방식 (월~일 7일 중 더 많은 날이 속한 달의 주차)
- `shared/domain/utils/period.py`의 `weeks_owned_by_month`, `week_of_month` 사용

### Summary 생성 task — 단일 task + Strategy 패턴

수동(`RequestSummaryUseCase`) / 자동(`dispatch_summaries_for_tz_task`) **모든 경로가 동일한 task** `worker.generate_summary` 를 호출한다. summary_type 별 데이터 소스 선택은 `retrospective/infrastructure/ai/strategies.py` 의 strategy 가 결정 — task 본체는 공통 골격(mark in_progress → AI 호출 → complete + notify, 실패 시 fail + notify) 만 담는다.

**Strategy 매트릭스** (`strategies.get_strategy(summary_type)`):

| summary_type | Strategy | 데이터 소스 |
|---|---|---|
| `weekly`  | `EntriesOnlyStrategy`   | 그 주의 일일 entry 전부 |
| `monthly` | `MonthlyHybridStrategy` | 주마다: weekly summary 있으면 그것, 없으면 entries. weekly 가 있어도 갱신 이후 추가된 entry 가 있으면 자동 첨부 (방식 B) — 데이터 손실 0 |
| `annual`  | `AnnualHybridStrategy`  | 월마다: monthly summary 있으면 그것, 없으면 그 달의 weekly summaries 로 보강. 둘 다 없으면 해당 월 스킵 |

자동 dispatcher 의 chain 구조는 weekly → monthly → annual 순서로 enqueue 되므로, 하위 단계 결과가 상위 단계에서 자동 활용된다.

### Summary 생성 사전 점검 — `GET /summaries/readiness`

monthly/annual 생성 직전에 FE 가 호출하는 사전 점검 API. **child summary 존재 여부가 아닌 entry 밀도** 기반.

| summary_type | expected | covered |
|---|---|---|
| monthly | 그 달의 일수 (28~31) | entry 가 있는 unique 날짜 수 |
| annual  | 12                  | entry 가 있는 월 수 |

`completenessRatio = covered / expected`. `< 0.7` 이면 `recommendation: "insufficient"` 반환 → FE 가 "데이터 부족, 그대로 진행?" 다이얼로그 띄움. 임계값은 `READINESS_THRESHOLD` 상수 (`get_summary_readiness.py`). weekly 호출은 `422 RETRO_SUMMARY_READINESS_UNSUPPORTED` 반환.

### 배포 순서 — worker → web

`worker.generate_summary` task 시그니처가 변경되거나 strategy 가 추가될 때는 항상 **worker 컨테이너를 먼저 배포한 뒤 web 컨테이너를 배포**한다.

- 반대 순서로 배포하면 web 이 신규 인자/strategy 로 task 를 enqueue 하지만 구 worker 가 그것을 처리하지 못해 실패.
- 진행 중 task 가 있을 수 있으니 worker 종료 전에 graceful shutdown (`celery worker --time-limit`) 활용.

---

## 20. 테스트

### 디렉토리 구조

```
tests/
├── conftest.py
├── factories/                       # 테스트 데이터 팩토리
│   ├── todo_factory.py
│   ├── user_factory.py
│   └── retro_factory.py
├── unit/                            # 순수 도메인 로직 — Docker 불필요
│   ├── test_todo_domain.py
│   └── test_retro_domain.py
└── integration/                     # TestClient + 실제 PostgreSQL
    └── api/
        ├── test_auth.py
        ├── test_todos.py
        └── test_retrospectives.py
```

### 테스트 데이터 팩토리

```python
# tests/factories/todo_factory.py
from datetime import datetime
from app.todo.domain.models.todo import Todo
from app.todo.domain.models.value_objects import TaskStatus

def make_todo(**kwargs) -> Todo:
    defaults = dict(
        id="todo_test000001",
        user_id="user_test000001",
        title="Test todo",
        status=TaskStatus.NOT_START,
        date_key="2026-05-21",
        created_at=datetime.utcnow(),
    )
    return Todo(**{**defaults, **kwargs})
```

### Fixture 패턴

```python
# tests/conftest.py
@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSession(engine) as session:
        yield session
        await session.rollback()

@pytest.fixture
def client(db_session: AsyncSession) -> TestClient:
    test_container = make_async_container(AppProvider(), TestRequestProvider(db_session))
    setup_dishka(test_container, app=app)
    with TestClient(app) as c:
        yield c
```

- 통합 테스트는 실제 PostgreSQL에 연결합니다. Mock DB를 사용하지 않습니다.
- 각 테스트는 트랜잭션 롤백으로 격리합니다.
- Anthropic, GitHub 등 외부 API는 테스트용 Provider로 교체합니다.

---

## 21. 코드 품질

### ruff 설정 (`pyproject.toml`)

```toml
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "B", "UP"]
```

### mypy 설정

```toml
[tool.mypy]
python_version = "3.12"
strict = true
plugins = ["pydantic.mypy", "sqlalchemy.ext.mypy.plugin"]
```

### 타입 힌트 규칙

- 모든 함수/메서드에 return type을 명시합니다.
- `Any` 사용을 금지합니다. 불가피하면 `# type: ignore[<error-code>]`에 이유를 주석으로 명시합니다.
- `Optional[X]` 대신 `X | None`, `Union[X, Y]` 대신 `X | Y`를 사용합니다.

### structlog 로깅

```python
import structlog
logger = structlog.get_logger(__name__)

# 항상 도메인 식별자를 포함합니다
logger.info("todo_created", todo_id=todo.id, user_id=user_id)
logger.error("github_api_failed", status_code=response.status_code, user_id=user_id)
```

---

*최종 업데이트: 2026-05-21*
