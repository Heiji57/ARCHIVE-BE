from datetime import datetime, timezone

from app.shared.domain.utils.id import generate_id
from app.topic.application.dtos.commands import GenerateDigestCommand
from app.topic.domain.exceptions.exceptions import (
    DigestAlreadyInProgressException,
    TopicNotFoundException,
)
from app.topic.domain.models.topic import TopicDigest
from app.topic.domain.models.value_objects import DigestStatus
from app.topic.domain.repositories.repository import (
    IDigestRateLimiter,
    ITopicDigestRepository,
    ITopicRepository,
)


class GenerateDigestUseCase:
    def __init__(
        self,
        topic_repo: ITopicRepository,
        digest_repo: ITopicDigestRepository,
        rate_limiter: IDigestRateLimiter,
    ) -> None:
        self._topic_repo = topic_repo
        self._digest_repo = digest_repo
        self._rate_limiter = rate_limiter

    async def execute(self, cmd: GenerateDigestCommand) -> TopicDigest:
        topic = await self._topic_repo.find_by_id(cmd.topic_id, cmd.user_id)
        if topic is None:
            raise TopicNotFoundException()

        existing = await self._digest_repo.find_by_topic(cmd.topic_id, cmd.user_id)
        if existing is not None and existing.status == DigestStatus.IN_PROGRESS:
            raise DigestAlreadyInProgressException()

        # 여기부터는 반드시 생성 작업이 큐에 들어간다 — 409 충돌은 세지 않는다.
        await self._rate_limiter.check_and_record(cmd.user_id)

        now = datetime.now(timezone.utc)
        if existing is not None:
            # Reset to pending so the worker can pick it up
            await self._digest_repo.update_status(existing.id, DigestStatus.PENDING)
            existing.status = DigestStatus.PENDING
            return existing

        digest = TopicDigest(
            id=generate_id("digest"),
            topic_id=cmd.topic_id,
            user_id=cmd.user_id,
            status=DigestStatus.PENDING,
            created_at=now,
        )
        return await self._digest_repo.save(digest)
