"""계정 삭제 뒤 작업(01 §3).

- `worker.revoke_account_tokens`: GitHub·Google 토큰 철회. 실패해도 3번 다시 시도한 뒤 끝낸다.
- `worker.purge_deleted_accounts`(하루): 지운 지 30일 지난 계정을 완전히 지운다.
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog
from redis.asyncio import Redis

from app.auth.infrastructure.external.account_deletion import REVOKE_TOKENS_KEY
from app.auth.infrastructure.storage.avatar_storage import LocalAvatarStorage
from app.data.infrastructure.export.storage import LocalExportStorage
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
    storage = LocalAvatarStorage(settings.auth.avatar_dir)
    exports = LocalExportStorage(settings.auth.export_dir)
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
                exports.remove(key)
            if user.avatar_key:
                await storage.remove(user.avatar_key)
            _log.info("account.purged", user_id=user.id)
        except Exception:
            # 계정별 격리 경계 — 한 계정의 실패가 다른 계정 정리를 막지 않게.
            _log.exception("account.purge_failed", user_id=user.id)
