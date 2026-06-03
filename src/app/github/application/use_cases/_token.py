from app.auth.domain.models.value_objects import OAuthProvider
from app.auth.domain.repositories.repository import IOAuthConnectionRepository
from app.github.domain.exceptions.exceptions import GitHubConnectionNotFoundException


async def get_github_access_token(
    oauth_repo: IOAuthConnectionRepository, user_id: str
) -> str:
    """Return the user's GitHub OAuth access_token or raise."""
    connections = await oauth_repo.find_by_user_id(user_id)
    github_conn = next(
        (c for c in connections if c.provider == OAuthProvider.GITHUB),
        None,
    )
    if github_conn is None:
        raise GitHubConnectionNotFoundException("Connect GitHub account first.")
    return github_conn.access_token
