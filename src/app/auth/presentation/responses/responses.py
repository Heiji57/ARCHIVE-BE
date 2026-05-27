from pydantic import BaseModel


class TokenResponse(BaseModel):
    access_token: str


class PreAuthTokenResponse(BaseModel):
    pre_auth_token: str
    requires_2fa: bool = True
