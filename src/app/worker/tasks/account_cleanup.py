"""계정 삭제 뒤 작업(01 §3).

- `worker.finish_account_deletion`: users.deleted_at 커밋을 확인한 뒤 토큰 표식·세션 폐기·사진 파일
  삭제, 외부 토큰 철회 작업 넘기기. 안 보이면 잠시 뒤 다시, 끝까지 안 보이면(롤백) 아무것도 안 한다.
- `worker.revoke_account_tokens`: GitHub·Google 토큰 철회. 실패해도 3번 다시 시도한 뒤 끝낸다.
- `worker.purge_deleted_accounts`(하루): 지운 지 30일 지난 계정을 완전히 지운다. 아무도 가리키지
  않는 프로필 사진 파일도 정리한다.
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog
from redis.asyncio import Redis

from app.auth.application.services.session_service import SessionService
from app.auth.application.use_cases.delete_account import FinishAccountDeletionUseCase
from app.auth.infrastructure.cache.auth_token import AuthTokenCache
from app.auth.infrastructure.external.account_deletion import (
    REVOKE_TOKENS_KEY,
    RedisDeletedAccountMarker,
)
from app.auth.infrastructure.storage.avatar_storage import make_avatar_storage
from app.data.infrastructure.export.storage import make_export_storage
from app.data.infrastructure.persistence.repositories.export_repo import ExportRepository
from app.shared.infrastructure.config.settings import get_settings
from app.user.infrastructure.persistence.account_purge import purge_unlinked_user_data
from app.user.infrastructure.persistence.repositories.user_repo import UserRepository
from app.worker.celery_app import celery_app
from app.worker.db import get_worker_session_factory

_log = structlog.get_logger(__name__)

ACCOUNT_RETENTION = timedelta(days=30)
_REVOKE_RETRIES = 3
_TIMEOUT = httpx.Timeout(10.0)


async def _revoke(client: httpx.AsyncClient, provider: str, token: str) -> bool:
    settings = get_settings()
    if provider == "github":
        cfg = settings.github_oauth
        resp = await client.request(
            "DELETE",
            f"https://api.github.com/applications/{cfg.client_id}/grant",
            auth=(cfg.client_id, cfg.client_secret),
            json={"access_token": token},
            headers={"Accept": "application/vnd.github+json"},
        )
        return resp.status_code in (204, 404, 422)  # 404/422 = 이미 무효
    if provider == "google":
        resp = await client.post(
            "https://oauth2.googleapis.com/revoke",
            data={"token": token},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        return resp.status_code in (200, 400)  # 400 invalid_token = 이미 무효
    return True


_FINISH_RETRIES = 5
_ORPHAN_AVATAR_AGE_SECONDS = 86400  # 방금 올린(아직 커밋 전일 수 있는) 파일은 건드리지 않게


@celery_app.task(name="worker.finish_account_deletion", bind=True, max_retries=_FINISH_RETRIES)
async def finish_account_deletion_task(
    self: Any, user_id: str, avatar_key: str | None, tokens_ref: str | None
) -> None:
    settings = get_settings()
    async with get_worker_session_factory().begin() as session:
        deleted = await UserRepository(session).is_deleted(user_id)
    redis = Redis.from_url(settings.redis.auth_url, decode_responses=True)
    try:
        if not deleted:
            # 요청 커밋보다 먼저 왔을 수 있다 — 잠시 뒤 다시(AsyncContextTask).
            if self.request.retries < _FINISH_RETRIES:
                raise self.retry(countdown=1)
            # 끝까지 안 보이면 요청이 롤백된 것 — 계정은 그대로이니 아무것도 하지 않는다.
            _log.warning("account.delete_not_committed", user_id=user_id)
            if tokens_ref:
                await redis.delete(REVOKE_TOKENS_KEY.format(ref=tokens_ref))
            return
        await FinishAccountDeletionUseCase(
            SessionService(AuthTokenCache(redis, settings.auth), settings.auth),
            RedisDeletedAccountMarker(redis, settings.auth.access_token_expire_minutes * 60),
            make_avatar_storage(settings),
        ).execute(user_id, avatar_key)
    finally:
        await redis.aclose()
    if tokens_ref:
        revoke_account_tokens_task.apply_async(args=[tokens_ref], queue="default")


@celery_app.task(
    name="worker.revoke_account_tokens", bind=True, max_retries=_REVOKE_RETRIES, ignore_result=True
)
async def revoke_account_tokens_task(self: Any, ref: str) -> None:
    """토큰은 인자가 아니라 Redis 키(`revoke_tokens:{ref}`)로 받는다 — 브로커에 남지 않게."""
    redis = Redis.from_url(get_settings().redis.auth_url, decode_responses=True)
    key = REVOKE_TOKENS_KEY.format(ref=ref)
    try:
        raw = await redis.get(key)
        if raw is None:
            return  # 이미 끝났거나 TTL 이 지남
        left: list[dict[str, str]] = []
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            for item in json.loads(raw):
                try:
                    ok = await _revoke(client, item["provider"], item["token"])
                except httpx.HTTPError:
                    ok = False
                if not ok:
                    left.append(item)
        if not left:
            await redis.delete(key)
            return
        if self.request.retries < _REVOKE_RETRIES:
            await redis.set(key, json.dumps(left), keepttl=True)
            raise self.retry(countdown=60 * (self.request.retries + 1))
        await redis.delete(key)
        # 끝까지 실패 — 토큰 값은 남기지 않고 종류만 기록한다.
        _log.warning("account.revoke_gave_up", providers=[i["provider"] for i in left])
    finally:
        await redis.aclose()


@celery_app.task(name="worker.purge_deleted_accounts")
async def purge_deleted_accounts_task() -> None:
    settings = get_settings()
    storage = make_avatar_storage(settings)
    exports = make_export_storage(settings)
    before = datetime.now(UTC) - ACCOUNT_RETENTION
    factory = get_worker_session_factory()
    async with factory.begin() as session:
        users = await UserRepository(session).find_deleted_before(before)
    for user in users:
        try:
            async with factory.begin() as session:
                export_files = await ExportRepository(session).file_keys_of(user.id)
                await purge_unlinked_user_data(session, user.id)
                await UserRepository(session).purge(user.id)
            for key in export_files:
                await exports.remove(key)
            if user.avatar_key:
                await storage.remove(user.avatar_key)
            _log.info("account.purged", user_id=user.id)
        except Exception:
            # 계정별 격리 경계 — 한 계정의 실패가 다른 계정 정리를 막지 않게.
            _log.exception("account.purge_failed", user_id=user.id)

    # 아무도 가리키지 않는 사진 파일(바꾼·지운 사진의 옛 파일) 정리.
    async with factory.begin() as session:
        referenced = await UserRepository(session).avatar_keys()
    for key in await storage.stale_keys(_ORPHAN_AVATAR_AGE_SECONDS):
        if key not in referenced:
            await storage.remove(key)
