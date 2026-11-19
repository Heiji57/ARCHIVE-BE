from dataclasses import dataclass

from app.shared.domain.models.base import BaseEntity
from app.user.domain.models.value_objects import Email


@dataclass(kw_only=True)
class User(BaseEntity):
    email: Email
    password_hash: str | None  # None — OAuth 전용 유저
    country: str
    region: str | None
    timezone: str
    display_name: str | None = None  # 1~50자, 없으면 FE 가 이메일 앞부분을 보인다
    avatar_key: str | None = None  # 프로필 사진 저장 키(사용자 id 가 드러나지 않는 임의 값)

    def is_oauth_only(self) -> bool:
        return self.password_hash is None
