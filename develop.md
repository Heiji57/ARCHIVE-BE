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
| AI | anthropic, openai |
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
    RETRO_SUMMARY_IN_PROGRESS = "RETRO_SUMMARY_IN_PROGRESS"
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
| `redis://redis:6379/2` | 앱 캐시 (GitHub 커밋, OAuth state, API 응답) | `RedisCache` 클래스 |

캐시 키 네이밍: `{도메인}:{식별자}:{목적}` 형식

```
github:commits:{user_id}:{repo_full_name}    # TTL: 300초
user:oauth_state:{state_value}               # TTL: 600초 (1회용)
summary:result:{retro_id}                    # TTL: 3600초
```

---

## 18. 인증 / 인가

### 인증 흐름

| 방식 | 흐름 |
|---|---|
| 이메일/패스워드 | `POST /auth/register` → `POST /auth/login` → JWT 발급 |
| GitHub OAuth | `GET /auth/github` → GitHub → `GET /auth/github/callback` → JWT 발급 |
| Google OAuth | `GET /auth/google` → Google → `GET /auth/google/callback` → JWT 발급 |
| TOTP 2FA | 1단계 로그인 → pre_auth 토큰 → `POST /auth/2fa/verify` → access 토큰 교환 |

### JWT 구조

```python
# 1단계 로그인 완료 후 발급 — 유효기간 5분, 2FA 검증 전용
{ "sub": "user_id", "type": "pre_auth", "exp": ... }

# 2FA 검증 완료 후 발급 — 유효기간 15분
{ "sub": "user_id", "type": "access", "exp": ... }

# Refresh Token — 유효기간 7일
{ "sub": "user_id", "type": "refresh", "exp": ... }
```

### 라우터 보호

```python
# 일반 인증 (2FA 미설정 사용자 또는 2FA 완료 사용자)
current_user: UserContext = Depends(get_current_user)      # type == "access"

# 2FA 1단계 완료 후 TOTP 입력 엔드포인트 전용
current_user: UserContext = Depends(get_pre_auth_user)     # type == "pre_auth"
```

2FA 미설정 사용자는 로그인 시 바로 `access` 토큰을 받습니다. 2FA 설정 사용자는 `pre_auth` → TOTP 검증 → `access` 순서를 거칩니다.

### OAuth state 보안

```python
import secrets

# 생성 — 암호학적으로 안전한 랜덤 값
state = secrets.token_urlsafe(32)

# Redis 저장 — TTL 10분, 콜백 후 즉시 삭제 (1회용)
await redis.setex(f"user:oauth_state:{state}", 600, user_session_id)

# 콜백 검증 — getdel로 읽는 동시에 삭제 (재사용 방지)
stored = await redis.getdel(f"user:oauth_state:{state}")
if not stored:
    raise OAuthStateInvalidException()
```

### OAuth 신규 사용자 온보딩 흐름 (국가 정보 수집)

OAuth 콜백에서 처음 보이는 사용자는 곧바로 계정을 만들지 않고 **임시 onboarding token**을 발급해 FE가 국가/하위지역을 입력하도록 유도합니다.

```
1. /auth/oauth/{provider}/callback
   ├─ provider 토큰 교환 + user_info 조회
   ├─ 분기:
   │   • 기존 사용자       → 일반 access/refresh 발급
   │   • 신규 사용자       → Redis에 onboarding payload 저장 (TTL 30분)
   │                       → HttpOnly Cookie `onboarding_token` 발급
   │                       → postMessage({ type: "oauth_onboarding_required" })
2. POST /auth/oauth/onboarding
   ├─ Cookie의 onboarding_token으로 Redis 조회 (consume)
   ├─ body { country, region? }  validation
   ├─ country/region → IANA tz 결정
   ├─ User + OAuthConnection 생성
   └─ refresh_token Cookie + access_token body
```

Redis 키 형식: `auth:onboarding:{token} → JSON {provider, provider_user_id, email}` (TTL 1800s).

### 사용자 타임존 & 국가

| 필드 | 의미 | 변경 API |
|---|---|---|
| `users.country` | ISO 3166-1 alpha-2 (`KR`, `US`, ...) | `PATCH /settings/country` (timezone 자동 재계산) |
| `users.region` | ISO 3166-2 (`US-CA`) — 다중 tz 국가만 사용 | `PATCH /settings/country` |
| `users.timezone` | IANA tz (`Asia/Seoul`) — AI 요약 스케줄링 기준 | `PATCH /settings/timezone` (단독 override) |

- 다중 tz 국가: `US, CA, RU, AU, BR, MX, ID, AR, CL, KZ, MN` — `region` 필수
- `resolve_timezone(country, region)`는 `shared/domain/utils/timezone.py`에서 결정
- AI 자동 요약은 **사용자 tz 기준 새벽 1시**에 트리거됨

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
