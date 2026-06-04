"""Session 정책 서비스 — server-side trust anchor 의 핵심.

본 모듈에서 결정되는 정책:
- RT 발급 (sessionId + secret, secret 은 hash 로만 저장)
- Rotation (모든 refresh 마다 RT 교체)
- Reuse detection: 폐기된 RT 재등장 → 해당 사용자 모든 세션 폐기 + 보안 로그
- Grace window: 동시 refresh race 시 직전 RT 를 짧게 허용 (false positive 방지)
- per-session metadata (device label, ip prefix, last_used_at) 갱신
"""
import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

from app.auth.domain.exceptions.exceptions import (
    RefreshTokenInvalidException,
    RefreshTokenReuseDetectedException,
)
from app.auth.infrastructure.cache.auth_token import AuthTokenCache, SessionRecord
from app.shared.domain.utils.id import generate_id
from app.shared.infrastructure.logger.security import get_security_logger

_GRACE_WINDOW_SECONDS = 5.0


@dataclass(frozen=True)
class RequestMeta:
    """세션 발급/갱신 시 함께 수집하는 클라이언트 컨텍스트."""
    user_agent: str | None
    ip: str | None


@dataclass(frozen=True)
class IssuedSession:
    refresh_token: str
    session_id: str


@dataclass(frozen=True)
class RotatedSession:
    refresh_token: str
    session_id: str
    user_id: str


class SessionService:
    def __init__(self, cache: AuthTokenCache) -> None:
        self._cache = cache
        self._log = get_security_logger()

    # ── 발급 ──────────────────────────────────────────────────────────────────
    async def issue(self, user_id: str, meta: RequestMeta) -> IssuedSession:
        session_id = generate_id("sess")
        secret = secrets.token_urlsafe(32)
        rt = f"{session_id}.{secret}"
        now = self._cache.now_epoch()

        record = SessionRecord(
            session_id=session_id,
            user_id=user_id,
            rt_hash=_sha256(secret),
            prev_rt_hash=None,
            prev_at=None,
            device_info=meta.user_agent,
            device_label=_device_label(meta.user_agent),
            ip_prefix=_ip_prefix(meta.ip),
            issued_at=now,
            last_used_at=now,
            rotation_counter=0,
        )
        await self._cache.save(record)
        return IssuedSession(refresh_token=rt, session_id=session_id)

    # ── 회전 (refresh) ────────────────────────────────────────────────────────
    async def rotate(self, raw_rt: str, meta: RequestMeta) -> RotatedSession:
        session_id, secret = self._split_rt(raw_rt)
        presented_hash = _sha256(secret)

        record = await self._cache.get(session_id)
        if record is None:
            # 세션 자체가 없음 — 두 가지 가능성:
            #  (a) 사용자가 logout/revoke 직후 → 정상적인 무효화
            #  (b) sessionId 추측 시도 → 무의미 (sessionId 는 opaque)
            # 어느 쪽이든 단순 401. (탈취 의심 카운트는 prev/current 모두 불일치할 때만 올린다)
            raise RefreshTokenInvalidException()

        now = self._cache.now_epoch()

        # 1) 현재 유효 RT 와 일치 → 정상 rotation
        if presented_hash == record.rt_hash:
            new_secret = secrets.token_urlsafe(32)
            new_hash = _sha256(new_secret)
            updated = SessionRecord(
                session_id=record.session_id,
                user_id=record.user_id,
                rt_hash=new_hash,
                prev_rt_hash=record.rt_hash,
                prev_at=now,
                device_info=meta.user_agent or record.device_info,
                device_label=_device_label(meta.user_agent) or record.device_label,
                ip_prefix=_ip_prefix(meta.ip) or record.ip_prefix,
                issued_at=record.issued_at,
                last_used_at=now,
                rotation_counter=record.rotation_counter + 1,
            )
            await self._cache.save(updated)
            return RotatedSession(
                refresh_token=f"{record.session_id}.{new_secret}",
                session_id=record.session_id,
                user_id=record.user_id,
            )

        # 2) 직전 RT 와 일치 AND grace 윈도 안 → 동시 refresh race
        if (
            record.prev_rt_hash is not None
            and presented_hash == record.prev_rt_hash
            and record.prev_at is not None
            and (now - record.prev_at) < _GRACE_WINDOW_SECONDS
        ):
            # 이미 새 RT 발급된 상태. 동일 RT 재발행하지 않고 현재 유효 RT 를 사용하도록 안내.
            # 두 번째 탭은 어차피 직후 새 access_token이 필요할 뿐 — 401 로 한 번 더 refresh 유도해도 되지만,
            # UX 안정성을 위해 access token 재발급만 허용한다. 신호: RotatedSession 의 refresh_token=빈문자.
            self._log.info(
                "session.refresh_grace_hit",
                session_id=record.session_id,
                user_id=record.user_id,
                age_sec=round(now - record.prev_at, 3),
            )
            # grace 응답: 새 RT 발급하지 않고 호출자가 기존 RT 를 그대로 다시 set 하도록 빈 token 반환
            return RotatedSession(
                refresh_token="",
                session_id=record.session_id,
                user_id=record.user_id,
            )

        # 3) 그 외 — 폐기된 RT 재등장 → 탈취 의심 → 전 세션 폐기
        await self._handle_reuse(record, presented_hash, meta, now)
        raise RefreshTokenReuseDetectedException()

    async def _handle_reuse(
        self,
        record: SessionRecord,
        presented_hash: str,
        meta: RequestMeta,
        now: float,
    ) -> None:
        purged = await self._cache.delete_all(record.user_id)
        self._log.warning(
            "session.refresh_reuse_detected",
            event="REFRESH_TOKEN_REUSE",
            user_id=record.user_id,
            triggering_session_id=record.session_id,
            presented_hash=presented_hash,
            current_hash=record.rt_hash,
            prev_hash=record.prev_rt_hash,
            prev_at=record.prev_at,
            now=now,
            purged_session_count=len(purged),
            purged_session_ids=purged,
            ip_prefix=_ip_prefix(meta.ip),
            device_label=_device_label(meta.user_agent),
            user_agent=meta.user_agent,
        )

    # ── 폐기 ──────────────────────────────────────────────────────────────────
    async def revoke(self, session_id: str, user_id: str) -> None:
        await self._cache.delete(session_id, user_id)
        self._log.info(
            "session.revoked",
            session_id=session_id,
            user_id=user_id,
        )

    async def revoke_all(self, user_id: str) -> None:
        purged = await self._cache.delete_all(user_id)
        self._log.info(
            "session.revoked_all",
            user_id=user_id,
            purged_session_count=len(purged),
        )

    async def revoke_others(self, user_id: str, keep_session_id: str) -> int:
        """현재 세션만 남기고 모두 폐기. 폐기된 개수 반환."""
        ids = await self._cache.list_session_ids(user_id)
        purged = 0
        for sid in ids:
            if sid == keep_session_id:
                continue
            await self._cache.delete(sid, user_id)
            purged += 1
        self._log.info(
            "session.revoked_others",
            user_id=user_id,
            keep_session_id=keep_session_id,
            purged_session_count=purged,
        )
        return purged

    # ── 조회 ──────────────────────────────────────────────────────────────────
    async def list_for_user(self, user_id: str) -> list[SessionRecord]:
        return await self._cache.list_records(user_id)

    async def get_session_id_from_rt(self, raw_rt: str) -> str | None:
        """RT에서 sessionId만 안전하게 추출 (검증 없이). 라우터의 현재-세션 표시용."""
        try:
            sid, _ = self._split_rt(raw_rt)
            return sid
        except RefreshTokenInvalidException:
            return None

    # ── 내부 helpers ──────────────────────────────────────────────────────────
    @staticmethod
    def _split_rt(raw_rt: str) -> tuple[str, str]:
        # RT 형식: "{sessionId}.{secret}". sessionId 는 "sess_" + 32hex 라 '.' 없음.
        parts = raw_rt.split(".", 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise RefreshTokenInvalidException()
        return parts[0], parts[1]


# ── 모듈 utils ────────────────────────────────────────────────────────────────
def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _ip_prefix(ip: str | None) -> str | None:
    """IPv4 → /24 마스킹. IPv6 → /48 prefix. 분석 통계용. 인증 판정에는 쓰지 않음."""
    if not ip:
        return None
    if ":" in ip:
        # IPv6 — 앞 3개 hextet
        parts = ip.split(":")
        return ":".join(parts[:3]) + "::/48"
    parts = ip.split(".")
    if len(parts) == 4:
        return ".".join(parts[:3])
    return None


_BROWSER_RX = re.compile(
    r"(Edg|OPR|Chrome|Safari|Firefox|MSIE)/[\d.]+", re.IGNORECASE
)
_OS_RX = re.compile(
    r"(Windows NT [\d.]+|Mac OS X [\d_.]+|Android [\d.]+|iPhone OS [\d_]+|Linux)",
    re.IGNORECASE,
)


def _device_label(ua: str | None) -> str | None:
    if not ua:
        return None
    b = _BROWSER_RX.search(ua)
    o = _OS_RX.search(ua)
    browser = b.group(1) if b else None
    if browser and browser.lower() == "opr":
        browser = "Opera"
    os_name = None
    if o:
        raw = o.group(1)
        if raw.startswith("Windows NT"):
            os_name = "Windows"
        elif raw.startswith("Mac OS X"):
            os_name = "macOS"
        elif raw.startswith("Android"):
            os_name = "Android"
        elif raw.startswith("iPhone OS"):
            os_name = "iOS"
        else:
            os_name = "Linux"
    if browser and os_name:
        return f"{browser} on {os_name}"
    if browser:
        return browser
    if os_name:
        return os_name
    return None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
