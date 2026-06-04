"""Refresh token / Session 캐시 — Redis 어댑터.

이 모듈은 raw CRUD만 담당한다. 정책(grace window, reuse detection, rotation 분기)은
SessionService(application layer) 에서 결정한다.

스키마:
  KEY  auth:session:{session_id}          JSON  → SessionRecord
  KEY  auth:user_sessions:{user_id}       Set   → {session_id, ...}
  TTL  refresh_token_expire_days * 86400
"""
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from redis.asyncio import Redis

from app.shared.infrastructure.config.auth import AuthConfig


@dataclass
class SessionRecord:
    session_id: str
    user_id: str
    rt_hash: str
    prev_rt_hash: str | None
    prev_at: float | None              # unix epoch (sec)
    device_info: str | None
    device_label: str | None
    ip_prefix: str | None
    issued_at: float
    last_used_at: float
    rotation_counter: int

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> "SessionRecord":
        return cls(**json.loads(raw))


class AuthTokenCache:
    def __init__(self, redis: Redis, config: AuthConfig) -> None:
        self._redis = redis
        self._ttl = config.refresh_token_expire_days * 86400

    # ── 키 helpers ────────────────────────────────────────────────────────────
    @staticmethod
    def _key_session(session_id: str) -> str:
        return f"auth:session:{session_id}"

    @staticmethod
    def _key_user_sessions(user_id: str) -> str:
        return f"auth:user_sessions:{user_id}"

    # ── CRUD ──────────────────────────────────────────────────────────────────
    async def save(self, record: SessionRecord) -> None:
        """신규 저장 또는 갱신. user_sessions Set 에도 등록."""
        pipe = self._redis.pipeline()
        pipe.setex(self._key_session(record.session_id), self._ttl, record.to_json())
        pipe.sadd(self._key_user_sessions(record.user_id), record.session_id)
        pipe.expire(self._key_user_sessions(record.user_id), self._ttl)
        await pipe.execute()

    async def get(self, session_id: str) -> SessionRecord | None:
        raw = await self._redis.get(self._key_session(session_id))
        if not raw:
            return None
        return SessionRecord.from_json(raw)

    async def delete(self, session_id: str, user_id: str) -> None:
        pipe = self._redis.pipeline()
        pipe.delete(self._key_session(session_id))
        pipe.srem(self._key_user_sessions(user_id), session_id)
        await pipe.execute()

    async def delete_all(self, user_id: str) -> list[str]:
        """user_id 의 모든 세션 폐기. 폐기된 sessionId 리스트 반환 (로깅용)."""
        sessions = await self._redis.smembers(self._key_user_sessions(user_id))
        if sessions:
            keys = [self._key_session(s) for s in sessions]
            await self._redis.delete(*keys)
        await self._redis.delete(self._key_user_sessions(user_id))
        return list(sessions)

    async def list_session_ids(self, user_id: str) -> list[str]:
        sessions = await self._redis.smembers(self._key_user_sessions(user_id))
        return list(sessions)

    async def list_records(self, user_id: str) -> list[SessionRecord]:
        ids = await self.list_session_ids(user_id)
        if not ids:
            return []
        keys = [self._key_session(sid) for sid in ids]
        raws = await self._redis.mget(*keys)
        result: list[SessionRecord] = []
        stale: list[str] = []
        for sid, raw in zip(ids, raws):
            if raw is None:
                stale.append(sid)
                continue
            result.append(SessionRecord.from_json(raw))
        if stale:
            await self._redis.srem(self._key_user_sessions(user_id), *stale)
        return result

    @staticmethod
    def now_epoch() -> float:
        return datetime.now(timezone.utc).timestamp()
