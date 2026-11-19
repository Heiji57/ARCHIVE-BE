from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

ExportScope = Literal["retro", "todo", "ai"]
ExportFormat = Literal["md", "json"]
ExportStatus = Literal["pending", "ready", "failed"]

EXPORT_SCOPES: tuple[ExportScope, ...] = ("retro", "todo", "ai")
EXPORT_FILE_RETENTION = timedelta(days=7)  # 파일 보관 — 지나면 지우고 410
EXPORT_URL_TTL = timedelta(hours=24)  # 내려받기 서명 URL 유효 시간
EXPORT_DAILY_LIMIT = 3  # 최근 24시간
EXPORT_STUCK_AFTER = timedelta(hours=1)  # 이보다 오래 pending 이면 워커가 죽은 것으로 본다


@dataclass
class ExportJob:
    id: str
    user_id: str
    scopes: list[ExportScope]
    format: ExportFormat
    status: ExportStatus
    created_at: datetime
    file_key: str | None = None
    ready_at: datetime | None = None
    expires_at: datetime | None = None  # 파일을 지우는 시각(ready_at + 7일)

    def is_expired(self, now: datetime) -> bool:
        return self.expires_at is not None and now >= self.expires_at
