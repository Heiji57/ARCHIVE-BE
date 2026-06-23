"""주간 요약 테스트용 시드 스크립트.

사용법:
    ACCESS_TOKEN=<bearer_token> python scripts/seed_weekly_test.py [--base-url http://localhost:8000] [--period-start 2026-06-23]

삽입 데이터:
    - journal entry 5개 (주간 Mon~Fri)
    - todo not-start  5개
    - todo in-progress 10개
    - todo done       12개
    → POST /summaries/generate?type=weekly&periodStart=<period_start> 호출
    → 상태 폴링 후 결과 출력
"""
import argparse
import os
import sys
import time

import httpx

BASE_URL = "http://localhost:8000"
API = "/api/v1"

ENTRIES = [
    {
        "date_key": "2026-06-23",
        "retro_type": "daily",
        "title": "모달 컴포넌트 구현 완료",
        "content": "사용자 설정 모달 컴포넌트를 완성했다. Pydantic 스키마와 FastAPI 라우터를 연동하면서 alias 처리 방식에서 약간 헤맸는데, model_config 설정으로 해결했다. 다음엔 camelCase alias 패턴을 미리 정의해두면 좋겠다.",
    },
    {
        "date_key": "2026-06-24",
        "retro_type": "daily",
        "title": "GitHub OAuth 링크 API 연동",
        "content": "이메일 로그인 유저가 GitHub 계정을 연결할 수 있도록 link/init 플로우를 FE와 연동했다. state 파라미터에 link_user_id를 담아 처리하는 구조가 깔끔했다. 단, 이미 다른 유저에 연결된 GitHub 계정으로 시도 시 에러 핸들링이 FE에서 부족해 UX가 불명확했다.",
    },
    {
        "date_key": "2026-06-25",
        "retro_type": "daily",
        "title": "JWT 토큰 스테일 버그 수정",
        "content": "account_type을 변경해도 기존 JWT에는 반영이 안 되는 문제를 발견했다. PATCH /auth/me 응답에 새 access_token을 포함시켜 FE가 즉시 교체하도록 수정했다. refresh 시에도 DB에서 최신 account_type을 조회하도록 RefreshTokenUseCase를 개선했다.",
    },
    {
        "date_key": "2026-06-26",
        "retro_type": "daily",
        "title": "AI 요약 None 반환 버그 원인 파악",
        "content": "gemini-2.5-flash의 thinking 모드와 response_schema가 충돌해 response.text가 None을 반환하는 문제를 확인했다. thinking_budget=0으로 설정해 구조화 출력 경로를 강제하도록 수정했다. 추가로 GetConnectionStatusUseCase에 구조적 로깅을 추가해 디버깅 가시성을 높였다.",
    },
    {
        "date_key": "2026-06-27",
        "retro_type": "daily",
        "title": "요약 409 정책 변경 및 테스트 환경 구성",
        "content": "기존 PENDING/IN_PROGRESS 상태의 요약에 재요청 시 409를 반환하던 정책을 덮어쓰기로 변경했다. 개발 단계에서 반복 테스트가 용이하도록 개선했다. 테스트 시드 스크립트를 작성해 재현 가능한 테스트 환경을 마련했다.",
    },
]

TODOS_NOT_START = [
    {"title": "다음 스프린트 태스크 분류 및 우선순위 결정", "date_key": "2026-06-28", "status": "not-start", "description": "백로그 정리 후 다음 주 작업 범위 확정"},
    {"title": "Redis 캐싱 전략 문서화", "date_key": "2026-06-28", "status": "not-start", "description": "현재 TTL 설정과 키 구조를 팀 문서에 정리"},
    {"title": "DB 인덱스 최적화 검토", "date_key": "2026-06-29", "status": "not-start", "description": "느린 쿼리 로그 분석 후 복합 인덱스 추가 여부 판단"},
    {"title": "E2E 테스트 시나리오 작성", "date_key": "2026-06-29", "status": "not-start", "description": "OAuth 플로우와 AI 요약 트리거 시나리오 우선 작성"},
    {"title": "Swagger 문서 자동 생성 검토", "date_key": "2026-06-29", "status": "not-start", "description": "api.yaml과 FastAPI OpenAPI 스펙 동기화 방안 조사"},
]

TODOS_IN_PROGRESS = [
    {"title": "사용자 인증 미들웨어 리팩토링", "date_key": "2026-06-23", "status": "in-progress", "description": "get_current_user 의존성 재사용성 개선"},
    {"title": "GitHub 저장소 연결 FE 에러 처리 개선", "date_key": "2026-06-23", "status": "in-progress", "description": "oauth_error 메시지 타입별 사용자 안내 문구 추가"},
    {"title": "알림 SSE 연결 안정성 테스트", "date_key": "2026-06-24", "status": "in-progress", "description": "클라이언트 재연결 시 누락 알림 처리 확인"},
    {"title": "Celery 워커 비동기 풀 설정 최적화", "date_key": "2026-06-24", "status": "in-progress", "description": "celery-aio-pool 동시성 파라미터 튜닝"},
    {"title": "회고 요약 스트리밍 API 안정성 개선", "date_key": "2026-06-25", "status": "in-progress", "description": "Redis pub/sub 연결 해제 시 클린업 처리"},
    {"title": "Pydantic v2 마이그레이션 잔여 작업", "date_key": "2026-06-25", "status": "in-progress", "description": "serialization_alias 일관성 검토"},
    {"title": "Docker Compose 개발 환경 개선", "date_key": "2026-06-26", "status": "in-progress", "description": "핫리로드와 볼륨 마운트 설정 정리"},
    {"title": "AI 프롬프트 품질 개선", "date_key": "2026-06-26", "status": "in-progress", "description": "weekly/monthly 프롬프트 출력 일관성 테스트"},
    {"title": "GitHub 커밋 매칭 로직 엣지케이스 처리", "date_key": "2026-06-27", "status": "in-progress", "description": "verified email 없는 유저의 커밋 매칭 정확도 개선"},
    {"title": "세션 보안 정책 문서화", "date_key": "2026-06-27", "status": "in-progress", "description": "refresh token rotation 및 reuse detection 정책 팀 공유"},
]

TODOS_DONE = [
    {"title": "account_type 도메인 모델 추가", "date_key": "2026-06-23", "status": "done", "description": "User 엔티티에 account_type 필드 및 is_developer() 메서드 추가"},
    {"title": "JWT 페이로드에 account_type 포함", "date_key": "2026-06-23", "status": "done", "description": "create_access_token 및 _decode 업데이트"},
    {"title": "GitHub API 개발자 계정 전용 게이팅", "date_key": "2026-06-24", "status": "done", "description": "_require_developer 의존성으로 모든 /github/* 엔드포인트 보호"},
    {"title": "Alembic 마이그레이션 019 작성", "date_key": "2026-06-24", "status": "done", "description": "users 테이블에 account_type VARCHAR(16) 컬럼 추가"},
    {"title": "UpdateProfileRequest camelCase alias 버그 수정", "date_key": "2026-06-24", "status": "done", "description": "accountType, displayName 필드에 alias 추가 및 populate_by_name 설정"},
    {"title": "PATCH /auth/me 응답에 새 access_token 포함", "date_key": "2026-06-25", "status": "done", "description": "account_type 변경 시 JWT 스테일 문제 해결"},
    {"title": "EntryResponse / EntryWithGithubResponse 분리", "date_key": "2026-06-25", "status": "done", "description": "개발자 계정 + GitHub 연결 여부에 따라 조건부 응답 반환"},
    {"title": "OAuthAccountAlreadyLinkedException api.yaml 반영", "date_key": "2026-06-25", "status": "done", "description": "AUTH_OAUTH_ACCOUNT_ALREADY_LINKED 에러 코드 문서화"},
    {"title": "GetConnectionStatusUseCase 로깅 추가", "date_key": "2026-06-26", "status": "done", "description": "not_found vs token_verify_failed 케이스 구분 로그"},
    {"title": "gemini-2.5-flash thinking_budget=0 설정", "date_key": "2026-06-26", "status": "done", "description": "response_schema와 thinking 모드 충돌로 인한 None 반환 수정"},
    {"title": "SummaryAlreadyInProgressException 제거", "date_key": "2026-06-27", "status": "done", "description": "PENDING/IN_PROGRESS 상태에서도 덮어쓰기 허용으로 정책 변경"},
    {"title": "UserContext.is_developer() 메서드 추가", "date_key": "2026-06-27", "status": "done", "description": "account_type 비교 로직 캡슐화"},
]


def print_step(msg: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print('='*60)


def post(client: httpx.Client, path: str, body: dict) -> dict:
    r = client.post(f"{BASE_URL}{API}{path}", json=body)
    if r.status_code not in (200, 201, 202):
        print(f"  [ERROR] POST {path} → {r.status_code}: {r.text[:300]}")
        sys.exit(1)
    return r.json()


def main() -> None:
    global BASE_URL
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--period-start", default="2026-06-23")
    args = parser.parse_args()

    BASE_URL = args.base_url

    token = os.environ.get("ACCESS_TOKEN")
    if not token:
        print("ERROR: ACCESS_TOKEN 환경변수가 필요합니다.")
        print("  export ACCESS_TOKEN=<your_jwt_token>")
        sys.exit(1)

    headers = {"Authorization": f"Bearer {token}"}

    with httpx.Client(headers=headers, timeout=30) as client:
        # ── 1. Journal entries ──────────────────────────────────────
        print_step(f"Journal Entry 5개 삽입 (주간 Mon~Fri)")
        for e in ENTRIES:
            res = post(client, "/entries", e)
            print(f"  ✓ [{e['date_key']}] {e['title']}")

        # ── 2. Todos ────────────────────────────────────────────────
        all_todos = TODOS_NOT_START + TODOS_IN_PROGRESS + TODOS_DONE
        counts = {"not-start": len(TODOS_NOT_START), "in-progress": len(TODOS_IN_PROGRESS), "done": len(TODOS_DONE)}
        print_step(f"Todo {len(all_todos)}개 삽입 (시작전 {counts['not-start']} / 진행중 {counts['in-progress']} / 완료 {counts['done']})")
        for t in all_todos:
            post(client, "/todos", t)
        print(f"  ✓ 전체 {len(all_todos)}개 삽입 완료")

        # ── 3. 주간 요약 생성 요청 ──────────────────────────────────
        period_start = args.period_start
        print_step(f"주간 요약 생성 요청 (periodStart={period_start})")
        res = client.post(
            f"{BASE_URL}{API}/summaries/generate",
            params={"type": "weekly", "periodStart": period_start},
        )
        if res.status_code not in (200, 202):
            print(f"  [ERROR] {res.status_code}: {res.text[:300]}")
            sys.exit(1)
        summary_id = res.json()["data"]["id"]
        print(f"  ✓ 요약 요청 완료 (id={summary_id})")

        # ── 4. 완료까지 폴링 ────────────────────────────────────────
        print_step("요약 완료 대기 중...")
        for attempt in range(30):
            time.sleep(3)
            r = client.get(f"{BASE_URL}{API}/summaries/{summary_id}")
            if r.status_code != 200:
                print(f"  [ERROR] GET /summaries/{summary_id} → {r.status_code}")
                sys.exit(1)
            data = r.json()["data"]
            status = data["status"]
            print(f"  [{attempt+1:02d}] status={status}")

            if status == "completed":
                print_step("요약 완료!")
                content = data.get("content", {})
                for key, items in content.items():
                    label = {"achievements": "성과", "challenges": "어려움", "learnings": "배움", "next_focus": "다음 집중"}.get(key, key)
                    print(f"\n  [{label}]")
                    for item in (items or []):
                        print(f"    • {item}")
                return

            if status == "failed":
                print_step("요약 실패 (status=failed)")
                print("  Celery 워커 로그에서 오류를 확인하세요.")
                sys.exit(1)

        print("\n  [TIMEOUT] 90초 내에 완료되지 않았습니다. 워커 상태를 확인하세요.")
        sys.exit(1)


if __name__ == "__main__":
    main()
