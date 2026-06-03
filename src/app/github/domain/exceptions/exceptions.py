from app.shared.domain.exceptions.base import BaseAppException


class GitHubRepositoryNotFoundException(BaseAppException):
    code = "GITHUB_REPOSITORY_NOT_FOUND"


class GitHubRepositoryAlreadyLinkedException(BaseAppException):
    code = "GITHUB_REPOSITORY_ALREADY_LINKED"


class GitHubConnectionNotFoundException(BaseAppException):
    """User has not connected GitHub via OAuth."""
    code = "GITHUB_CONNECTION_NOT_FOUND"


class GitHubTokenInvalidException(BaseAppException):
    """GitHub returned 401 — token expired/revoked, user must re-auth."""
    code = "GITHUB_TOKEN_INVALID"


class GitHubRateLimitedException(BaseAppException):
    code = "GITHUB_RATE_LIMITED"


class GitHubApiUnavailableException(BaseAppException):
    code = "GITHUB_API_UNAVAILABLE"
