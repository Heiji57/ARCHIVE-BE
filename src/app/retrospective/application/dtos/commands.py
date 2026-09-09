from dataclasses import dataclass


@dataclass(frozen=True)
class CreateEntryCommand:
    user_id: str
    date_key: str
    # None/공백이면 서버가 locale 기반 기본 제목을 채운다.
    title: str | None
    content: str
    retro_type: str


@dataclass(frozen=True)
class UpsertEntryCommand:
    entry_id: str
    user_id: str
    date_key: str
    # 빈 문자열이면 서버가 locale 기반 기본 제목을 채운다.
    title: str | None
    content: str
    retro_type: str
