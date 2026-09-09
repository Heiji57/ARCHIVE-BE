from dataclasses import dataclass

from app.retrospective.domain.models.value_objects import RetroType
from app.shared.domain.models.base import BaseEntity


@dataclass(kw_only=True)
class JournalEntry(BaseEntity):
    user_id: str
    date_key: str  # YYYY-MM-DD
    title: str
    content: str
    retro_type: RetroType
    folder_id: str | None = None


@dataclass(frozen=True, kw_only=True)
class JournalEntryMeta:
    """본문 없이 식별·표시에만 필요한 필드를 담는 읽기 모델.

    `content`(회고 본문)와 `content_tsv`(전문검색 벡터)는 행마다 가장 큰 컬럼인데,
    목록·매칭처럼 "무엇이 있는지"만 알면 되는 경로에서는 읽지 않고 버려진다.
    엔티티를 통째로 실어오면 그 비용이 그대로 나가므로, 그런 경로는 이 모델로 받는다.
    """

    id: str
    date_key: str  # YYYY-MM-DD
    title: str
    retro_type: RetroType
