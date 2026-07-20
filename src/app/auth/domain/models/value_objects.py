from enum import StrEnum


class OAuthProvider(StrEnum):
    GITHUB = "github"
    GOOGLE = "google"


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"
