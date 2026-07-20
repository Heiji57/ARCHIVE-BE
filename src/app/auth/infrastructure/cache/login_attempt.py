"""로그인 실패 rate-limit (Redis 고정 윈도우 카운터).

목적: 자격증명 무차별 대입(brute-force) 차단. 로그인 엔드포인트에는 lockout/throttle 이
없어 무제한 시도가 가능했다(pentest 확인).

키 = (email + IP) 조합. email 단독으로 잠그면 공격자가 임의 계정을 일부러 잠그는 DoS 가
가능하므로, IP 를 함께 묶어 '공격 출처'만 차단하고 피해자 본인 로그인은 보호한다.
분산(다수 IP) 대입은 완화만 됨 — 필요 시 per-IP 전역 한도를 2차로 얹을 수 있다.

정책: window(기본 15분) 안에서 max(기본 10회) 실패 시 잠금. 첫 실패 때만 TTL 설정
(고정 윈도우) → window 경과 후 자동 리셋. 성공 로그인 시 즉시 카운터 삭제.
"""
from redis.asyncio import Redis

from app.shared.infrastructure.config.auth import AuthConfig


class LoginAttemptCache:
    def __init__(self, redis: Redis, config: AuthConfig) -> None:
        self._redis = redis
        self._max = config.login_max_attempts
        self._window = config.login_attempt_window_seconds

    def _key(self, email: str, ip: str | None) -> str:
        return f"auth:login:fail:{email}:{ip or 'noip'}"

    async def is_locked(self, email: str, ip: str | None) -> bool:
        raw = await self._redis.get(self._key(email, ip))
        return raw is not None and int(raw) >= self._max

    async def record_failure(self, email: str, ip: str | None) -> None:
        key = self._key(email, ip)
        count = await self._redis.incr(key)
        if count == 1:
            # 첫 실패에만 TTL — 고정 윈도우(첫 실패 기준 window 초 후 리셋)
            await self._redis.expire(key, self._window)

    async def reset(self, email: str, ip: str | None) -> None:
        await self._redis.delete(self._key(email, ip))
