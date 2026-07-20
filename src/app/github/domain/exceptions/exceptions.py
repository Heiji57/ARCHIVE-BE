from app.shared.domain.exceptions.base import BaseAppException


class DeveloperAccountRequiredException(BaseAppException):
    """GitHub 기능은 developer 계정 전용이다."""
    code = "DEVELOPER_ACCOUNT_REQUIRED"


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


class GitHubPushTargetNotSetException(BaseAppException):
    """User has not designated a push target repository."""
    code = "GITHUB_PUSH_TARGET_NOT_SET"


class GitHubPushFailedException(BaseAppException):
    """Push to GitHub failed (conflict / permission / network)."""
    code = "GITHUB_PUSH_FAILED"


class GitHubRepositoryNotLinkedException(BaseAppException):
    """Specified repository ID is not in the user's linked set."""
    code = "GITHUB_REPOSITORY_NOT_LINKED"
