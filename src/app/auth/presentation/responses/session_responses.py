from datetime import datetime

from pydantic import BaseModel, Field

from app.auth.application.use_cases.list_sessions import SessionView


class SessionResponse(BaseModel):
    session_id: str = Field(serialization_alias="sessionId")
    device_label: str | None = Field(serialization_alias="deviceLabel")
    device_info: str | None = Field(serialization_alias="deviceInfo")
    ip_prefix: str | None = Field(serialization_alias="ipPrefix")
    issued_at: datetime = Field(serialization_alias="issuedAt")
    last_used_at: datetime = Field(serialization_alias="lastUsedAt")
    rotation_counter: int = Field(serialization_alias="rotationCounter")
    is_current: bool = Field(serialization_alias="isCurrent")

    model_config = {"populate_by_name": True}

    @classmethod
    def from_view(cls, view: SessionView) -> "SessionResponse":
        return cls(
            session_id=view.session_id,
            device_label=view.device_label,
            device_info=view.device_info,
            ip_prefix=view.ip_prefix,
            issued_at=view.issued_at,
            last_used_at=view.last_used_at,
            rotation_counter=view.rotation_counter,
            is_current=view.is_current,
        )


class SessionListResponse(BaseModel):
    sessions: list[SessionResponse]


class RevokeOthersResponse(BaseModel):
    revoked_count: int = Field(serialization_alias="revokedCount")

    model_config = {"populate_by_name": True}
