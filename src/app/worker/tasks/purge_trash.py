"""worker.purge_trash — 하루 한 번, 휴지통에 30일 넘게 있던 할 일·회고를 영구 삭제한다.

임베딩(`todo_embeddings`)·청크(`entry_chunks`)도 함께 지운다(TrashUseCase.purge_expired).
"""

from datetime import UTC, datetime

import structlog

from app.data.application.use_cases.trash import TrashUseCase
from app.data.domain.models.trash import TRASH_RETENTION
from app.worker.celery_app import celery_app
from app.worker.tasks.run_ai_turn import _get_container

_log = structlog.get_logger(__name__)


@celery_app.task(name="worker.purge_trash")
async def purge_trash_task() -> None:
    before = datetime.now(UTC) - TRASH_RETENTION
    async with _get_container()() as request:
        removed = await (await request.get(TrashUseCase)).purge_expired(before)
    if removed:
        _log.info("trash.purged", rows=removed)
