# 새 기능 / 엔드포인트 추가 체크리스트

새 기능·엔드포인트를 추가할 때 아래 레이어 순서로 구현하고, 각 항목을 빠짐없이 점검한다.
(모듈 구조는 `CLAUDE.md` 의 "Module Structure Convention" 과 1:1 대응된다.)

## 구현 순서 (Domain → Presentation)

- [ ] **Domain model** — 엔티티/VO (`{module}/domain/models/`). `BaseEntity`(id/created_at/updated_at) 상속, ID 는 `generate_id("{prefix}")`.
- [ ] **Domain exception** — 새 도메인 예외가 필요하면 `{module}/domain/exceptions/` 에 추가.
- [ ] **Repository 인터페이스** — ABC 메서드 시그니처 (`{module}/domain/repositories/`).
- [ ] **DTO** — Command/Query (`{module}/application/dtos/`).
- [ ] **Use Case** — 비즈니스 로직 (`{module}/application/use_cases/`).
- [ ] **Repository 구현체** — SQLAlchemy 구현 (`{module}/infrastructure/persistence/repositories/`) + ORM 모델(`.../models/`).
- [ ] **Request/Response 스키마** — Pydantic (`{module}/presentation/requests|responses/`). 응답은 `ApiResponse[T]` 래퍼.
- [ ] **Router** — FastAPI 라우터. 인증 필요 시 `current_user: UserContext = Depends(get_current_user)`.

## 배선(Wiring) — 누락 최다 지점

- [ ] **DI 등록** — 신규 repository/use_case 를 `shared/infrastructure/container/providers.py` 에 `@provide` 로 등록. **빠뜨리면 런타임에 DI 해석 실패.**
- [ ] **라우터 등록** — `main.py` 의 `create_app()` 에 `app.include_router()` 추가.

## 계약 & 스키마

- [ ] **Migration** — 스키마 변경 시 `migrations/versions/` 에 Alembic 파일 추가.
- [ ] **api.yaml (SST)** — 엔드포인트 정의 추가/수정. 새 도메인 예외를 던지면:
  - [ ] `shared/infrastructure/errors/handler.py` 의 `_STATUS_MAP` 에 HTTP 상태 매핑
  - [ ] 해당 엔드포인트 `x-error-codes` 에 코드 명시
  - [ ] 공통 응답(`Unauthorized_401`, `Conflict_409` 등) description 코드 목록에 추가
- [ ] **타임존/기간 정책** — "오늘/이번 주" 등 기간 계산은 서버 UTC 가 아니라 사용자 tz 기준. `shared/domain/utils/period.py` 사용.

## 검증

- [ ] **테스트** — 테스트 코드가 있는 모듈이면 해당 시 추가. (프로젝트에 강제 테스트 워크플로우는 아직 없음 — 있을 때만.)
- [ ] 구현 완료 후 `review-checklist.md` 로 자기검증.
