from dataclasses import dataclass
from datetime import datetime

# ID type aliases — 도메인 간 명시적 구분
UserId = str
OAuthId = str
TokenId = str
TodoId = str
EntryId = str
SummaryId = str
NotificationId = str


@dataclass(kw_only=True)
class BaseEntity:
    id: str
    created_at: datetime
    updated_at: datetime | None = None
