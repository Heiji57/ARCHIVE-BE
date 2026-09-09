from dataclasses import dataclass


@dataclass(frozen=True)
class CreateTopicCommand:
    user_id: str
    name: str
    description: str = ""


@dataclass(frozen=True)
class UpdateTopicCommand:
    """name/description 은 None = 미전송(변경 없음). 빈 문자열은 description 비우기로 유효."""

    user_id: str
    topic_id: str
    name: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class DeleteTopicCommand:
    user_id: str
    topic_id: str


@dataclass(frozen=True)
class GenerateDigestCommand:
    user_id: str
    topic_id: str
