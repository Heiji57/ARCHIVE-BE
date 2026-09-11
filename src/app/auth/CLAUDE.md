# Auth 모듈 컨벤션

이 디렉토리(`src/app/auth/`)에서 작업할 때 적용되는 컨벤션. 루트 `CLAUDE.md`의 Key Conventions에서 이관됨.

- **Session 보안 정책**: Refresh token = `{sessionId}.{secret}` 형식. 모든 refresh 시 rotation + reuse detection. 폐기된 RT 재등장 시 해당 사용자의 모든 세션 즉시 폐기 + `security` structlog 채널에 `session.refresh_reuse_detected` 로깅. 동시 refresh race 는 `SESSION_GRACE_WINDOW_SECONDS`(기본 5초) grace window 로 흡수 (`session.refresh_grace_hit` 로깅). 세션 정책 본체는 `auth/application/services/session_service.py`. Redis 캐시는 raw CRUD 만 담당 (`auth/infrastructure/cache/auth_token.py`).
- **운영 파라미터 (TTL/window) env 화**: 모든 시간 기반 파라미터는 `.env` 에서 관리한다. `OAUTH_STATE_TTL_SECONDS`, `ONBOARDING_TOKEN_TTL_SECONDS`, `PASSWORD_RESET_TTL_SECONDS`, `PASSWORD_RESET_COOLDOWN_TTL_SECONDS`, `SESSION_GRACE_WINDOW_SECONDS`. 기본값은 `shared/infrastructure/config/auth.py`의 `AuthConfig`. 라우터의 cookie max-age는 별도 env 가 아니라 `refresh_token_expire_days` / `onboarding_token_ttl_seconds`에서 derive — 항상 Redis TTL과 동기화 보장.
- **OAuth Link 흐름**: 로그인된 사용자의 provider 계정 link 는 `POST /auth/oauth/{provider}/link/init` (Bearer) 로 시작. 응답의 `authorizeUrl` 을 FE 가 popup 으로 직접 연다. callback URL 은 일반 로그인과 동일 — state 에 저장된 `link_user_id` 로 분기.
- **OAuth Callback URL**: dev/prod 모두 **FE proxy origin** (예: `http://localhost:5173/api/v1/auth/oauth/{provider}/callback`) 으로 통일. callback HTML 의 `window.opener.postMessage` 가 FE origin 으로 도달해야 origin 검증을 통과한다.
