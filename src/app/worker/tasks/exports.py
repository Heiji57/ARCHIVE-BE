"""내보내기(12 §2).

- `worker.build_export`: zip 을 만들고 상태를 ready 로, 완료 알림
  (category: system, 링크 {kind: export, id}).
  실패하면 failed — 사용자가 다시 요청한다(자동 재시도 없음).
- `worker.purge_exports`(하루): 보관 7일이 지난 파일을 지운다(행은 남겨 GET 이 410).
"""

import json
import tempfile
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from redis.asyncio import Redis

from app.data.domain.models.export import EXPORT_FILE_RETENTION
from app.data.infrastructure.export.builder import build_export
from app.data.infrastructure.export.storage import make_export_storage
from app.data.infrastructure.persistence.repositories.export_repo import ExportRepository
from app.notification.application.services.notifier import (
    STREAM_CHANNEL,
    Notifier,
    should_push_now,
    stream_payload,
)
from app.notification.domain.models.value_objects import NotificationCategory, NotificationType
from app.notification.infrastructure.persistence.repositories.notification_repo import (
    NotificationRepository,
)
from app.settings.infrastructure.persistence.repositories.user_settings_repo import (
    UserSettingsRepository,
)
from app.shared.infrastructure.config.settings import get_settings
from app.user.infrastructure.persistence.repositories.user_repo import UserRepository
from app.worker.celery_app import celery_app
from app.worker.db import get_worker_session_factory

_log = structlog.get_logger(__name__)

_DONE_TEXT = {
    "ko": ("내보내기", "내보내기 파일이 준비됐어요. 7일 동안 내려받을 수 있어요"),
    "en": ("Export", "Your export is ready. You can download it for 7 days"),
}


# BackgroundTasks 는 이 스택(dishka 미들웨어)에서 요청 세션 커밋보다 먼저 돈다 — 워커가 아직
# 커밋 안 된 행을 읽을 수 있으므로, 안 보이면 잠시 뒤 다시(요약 워커와 같은 방식, AsyncContextTask).
_VISIBILITY_RETRIES = 5


@celery_app.task(name="worker.build_export", bind=True, max_retries=_VISIBILITY_RETRIES)
async def build_export_task(self: Any, export_id: str) -> None:
    settings = get_settings()
    storage = make_export_storage(settings)
    factory = get_worker_session_factory()
    async with factory.begin() as session:
        job = await ExportRepository(session).get(export_id)
    if job is None:
        if self.request.retries < _VISIBILITY_RETRIES:
            raise self.retry(countdown=1)
        # 끝까지 안 보이면 요청이 롤백된 것 — 만들 것이 없다.
        _log.warning("export.row_not_visible", export_id=export_id)
        return
    if job.status != "pending":
        return
    structlog.contextvars.bind_contextvars(user_id=job.user_id)
    key = f"{job.id}.zip"
    try:
        # 임시 디렉토리에 다 만든 뒤 저장소로 넘긴다 — 반쯤 만든 파일이 저장소에 보이지 않게.
        with tempfile.TemporaryDirectory(prefix="export-") as tmp:
            target = Path(tmp) / key
            async with factory.begin() as session:
                await build_export(session, job, target)
            await storage.save(key, target)
    except Exception:
        # 태스크 최상위 경계 — failed 로 닫는다(pending 으로 남으면 새 요청을 막는다).
        _log.exception("export.build_failed", export_id=export_id)
        async with factory.begin() as session:
            await ExportRepository(session).save(replace(job, status="failed"))
        return

    now = datetime.now(UTC)
    ready = replace(
        job, status="ready", file_key=key, ready_at=now, expires_at=now + EXPORT_FILE_RETENTION
    )
    async with factory.begin() as session:
        await ExportRepository(session).save(ready)
    try:
        await _notify_ready(job.user_id, job.id)
    except Exception:
        # 알림 실패가 이미 끝난 내보내기를 되돌리지 않게 — 기록만(FE 는 GET 으로 상태를 본다).
        _log.exception("export.notify_failed", export_id=export_id)


async def _notify_ready(user_id: str, export_id: str) -> None:
    settings = get_settings()
    async with get_worker_session_factory().begin() as session:
        settings_repo = UserSettingsRepository(session)
        user_settings = await settings_repo.find_by_user_id(user_id)
        locale = (user_settings.locale if user_settings else None) or "ko"
        title, message = _DONE_TEXT["ko" if locale.startswith("ko") else "en"]
        notification = await Notifier(
            NotificationRepository(session), settings_repo, UserRepository(session)
        ).notify(
            user_id,
            type=NotificationType.SUCCESS,
            category=NotificationCategory.SYSTEM,
            title=title,
            message=message,
            link={"kind": "export", "id": export_id},
            settings=user_settings,
        )
    if notification is not None and should_push_now(notification):
        redis = Redis.from_url(settings.redis.cache_url, decode_responses=True)
        try:
            await redis.publish(
                STREAM_CHANNEL.format(user_id=user_id),
                json.dumps(stream_payload(notification)),
            )
        finally:
            await redis.aclose()


@celery_app.task(name="worker.purge_exports")
async def purge_exports_task() -> None:
    storage = make_export_storage(get_settings())
    async with get_worker_session_factory().begin() as session:
        repo = ExportRepository(session)
        for job in await repo.find_files_expired(datetime.now(UTC)):
            if job.file_key:
                await storage.remove(job.file_key)
            await repo.save(replace(job, file_key=None))
