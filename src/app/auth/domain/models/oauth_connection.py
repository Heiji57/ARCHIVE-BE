from dataclasses import dataclass

from app.auth.domain.models.value_objects import OAuthProvider
from app.shared.domain.models.base import BaseEntity


@dataclass(kw_only=True)
class OAuthConnection(BaseEntity):
    user_id: str
    provider: OAuthProvider
    provider_user_id: str
    access_token: str
    provider_login: str | None = None    # provider 사용자명 캐시 (GitHub `login` 등)
    provider_verified_emails: list[str] | None = None
    """provider 계정에 verified 등록된 email 목록 캐시.
    GitHub 의 경우 `/user/emails` 응답 중 verified=true 만. None=미조회, []=조회했으나 비어있음.
    `GET /github/commits` 에서 author/committer email 매칭에 사용."""
