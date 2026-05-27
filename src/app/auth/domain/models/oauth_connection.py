from dataclasses import dataclass

from app.auth.domain.models.value_objects import OAuthProvider
from app.shared.domain.models.base import BaseEntity


@dataclass(kw_only=True)
class OAuthConnection(BaseEntity):
    user_id: str
    provider: OAuthProvider
    provider_user_id: str
    access_token: str
