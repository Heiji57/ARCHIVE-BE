# Harness — AI 작업 오케스트레이션

이 폴더는 AI(Claude Code)가 이 저장소에서 서버 개발을 수행할 때의 **사고 순서와 검증 절차**를 정의한다.
프로젝트 "설명"은 `CLAUDE.md` / `develop.md` / `api.yaml` 이 담당하고, 여기(harness)는 **"어떤 순서로 생각하고 무엇을 검증할지"** 만 담당한다.

> 강제력이 필요한 규칙(모델 선택, Pre-Implementation Workflow)은 `CLAUDE.md` 에 남아 항상 로드된다.
> 이 폴더의 상세 체크리스트는 **해당 작업 유형일 때만** 읽는다 — 무조건 다 읽지 않는다(컨텍스트 비용 절약).

## 파일 구성 (SRP)

| 파일 | 단일 책임 |
|---|---|
| `mission.md` | AI 의 최우선 목표와 성공 기준 (항상 로드 — `CLAUDE.md` 에서 `@import`) |
| `feature-checklist.md` | **새 기능/엔드포인트 추가** 작업 전용 레이어 체크리스트 |
| `review-checklist.md` | **구현 완료 후** 자기검증(reflection) 체크리스트 |

## 로딩 규칙 (작업 유형 → 읽을 것)

무조건 전부 읽지 말고, 작업을 먼저 분류한 뒤 필요한 것만 읽는다.

```
작업 분류
  ├─ 새 기능 / 새 엔드포인트 추가
  │     → feature-checklist.md 를 읽고 레이어 순서대로 구현
  │     → 관련 모듈의 코드만 Read (예: todo 작업이면 todo/**, notification 은 읽지 않음)
  │     → api 응답/에러 변경 시에만 api.yaml 해당 블록 Read
  │
  ├─ 버그 수정 / 리팩토링
  │     → 영향 파일 + 같은 모듈만 Read
  │     → api.yaml 은 응답 계약이 바뀔 때만 Read
  │
  └─ 단순 질문 / 코드 설명 / 현황 파악
        → 하네스 절차 생략 (CLAUDE.md 규정)

구현 완료 후 (모든 코드 수정 작업 공통)
      → review-checklist.md 로 자기검증
      → CLAUDE.md 의 "서브 sonnet 검증" 단계와 연결
```

## Context Priority (컨텍스트 우선순위)

한정된 컨텍스트를 쓸 때 아래 우선순위로 읽는다. 상위에서 답이 나오면 하위는 읽지 않는다.

1. 현재 수정 대상 파일
2. 같은 모듈의 인접 파일 (같은 레이어 + 바로 위/아래 레이어)
3. 관련 인터페이스 (repository ABC, DTO)
4. `api.yaml` 해당 엔드포인트 블록 (응답/에러 계약이 걸릴 때만)
5. `CLAUDE.md` Key Conventions (해당 정책이 걸릴 때만)
6. `develop.md` (전체 맥락이 꼭 필요할 때만 — 66KB, 마지막 수단)
