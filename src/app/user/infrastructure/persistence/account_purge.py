"""지운 계정의 완전 삭제(01 §3) — users FK(CASCADE)가 없는 사용자 데이터를 먼저 지운다.

나머지(할 일·회고·폴더·템플릿·요약·알림·설정·GitHub·태그·캘린더·AI·내보내기 기록 …)는
users 행을 지울 때 FK ON DELETE CASCADE 로 함께 지워진다. Google Calendar 에 보낸 일정은
사용자의 Google 데이터라 지우지 않는다.
"""

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.infrastructure.database.soft_delete import INCLUDE_DELETED
from app.topic.infrastructure.persistence.models.chunk_model import (
    EmbeddingQueueModel,
    EntryChunkModel,
    TodoEmbeddingModel,
)
from app.topic.infrastructure.persistence.models.topic_model import TopicDigestModel, TopicModel

# FK 로 users 에 묶이지 않은 사용자 소유 테이블 — 새로 생기면 여기 더한다.
_UNLINKED = (EntryChunkModel, TodoEmbeddingModel, EmbeddingQueueModel, TopicDigestModel, TopicModel)


async def purge_unlinked_user_data(session: AsyncSession, user_id: str) -> None:
    for model in _UNLINKED:
        await session.execute(
            delete(model).where(model.user_id == user_id).execution_options(**INCLUDE_DELETED)
        )
