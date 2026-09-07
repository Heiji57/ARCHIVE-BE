from dataclasses import dataclass


@dataclass(frozen=True)
class CreateTopicCommand:
    user_id: str
    name: str
    description: str = ""


@dataclass(frozen=True)
class DeleteTopicCommand:
    user_id: str
    topic_id: str


@dataclass(frozen=True)
class GenerateDigestCommand:
    user_id: str
    topic_id: str
