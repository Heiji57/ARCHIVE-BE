from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.github.domain.models.github_repository import GitHubRepository
from app.github.domain.repositories.repository import IGitHubRepositoryRepository
from app.github.infrastructure.persistence.models.github_repository_model import GitHubRepositoryModel


class GitHubRepositoryRepository(IGitHubRepositoryRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, repo: GitHubRepository) -> GitHubRepository:
        model = self._to_model(repo)
        merged = await self._session.merge(model)
        await self._session.flush()
        return self._to_entity(merged)

    async def save_many(self, repos: list[GitHubRepository]) -> list[GitHubRepository]:
        saved: list[GitHubRepository] = []
        for repo in repos:
            merged = await self._session.merge(self._to_model(repo))
            saved.append(self._to_entity(merged))
        await self._session.flush()
        return saved

    async def find_by_id(self, id: str, user_id: str) -> GitHubRepository | None:
        result = await self._session.execute(
            select(GitHubRepositoryModel).where(
                GitHubRepositoryModel.id == id,
                GitHubRepositoryModel.user_id == user_id,
            )
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def find_by_user(self, user_id: str) -> list[GitHubRepository]:
        result = await self._session.execute(
            select(GitHubRepositoryModel)
            .where(GitHubRepositoryModel.user_id == user_id)
            .order_by(GitHubRepositoryModel.full_name.asc())
        )
        return [self._to_entity(m) for m in result.scalars().all()]

    async def find_commit_read_enabled_by_user(
        self, user_id: str
    ) -> list[GitHubRepository]:
        result = await self._session.execute(
            select(GitHubRepositoryModel)
            .where(
                GitHubRepositoryModel.user_id == user_id,
                GitHubRepositoryModel.commit_read_enabled.is_(True),
            )
            .order_by(GitHubRepositoryModel.full_name.asc())
        )
        return [self._to_entity(m) for m in result.scalars().all()]

    async def find_by_github_id(
        self, user_id: str, github_repo_id: int
    ) -> GitHubRepository | None:
        result = await self._session.execute(
            select(GitHubRepositoryModel).where(
                GitHubRepositoryModel.user_id == user_id,
                GitHubRepositoryModel.github_repo_id == github_repo_id,
            )
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def delete(self, id: str, user_id: str) -> None:
        await self._session.execute(
            delete(GitHubRepositoryModel).where(
                GitHubRepositoryModel.id == id,
                GitHubRepositoryModel.user_id == user_id,
            )
        )

    async def delete_all_by_user(self, user_id: str) -> None:
        await self._session.execute(
            delete(GitHubRepositoryModel).where(GitHubRepositoryModel.user_id == user_id)
        )

    def _to_model(self, entity: GitHubRepository) -> GitHubRepositoryModel:
        return GitHubRepositoryModel(
            id=entity.id,
            user_id=entity.user_id,
            github_repo_id=entity.github_repo_id,
            owner=entity.owner,
            name=entity.name,
            full_name=entity.full_name,
            is_private=entity.is_private,
            default_branch=entity.default_branch,
            html_url=entity.html_url,
            commit_read_enabled=entity.commit_read_enabled,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    def _to_entity(self, model: GitHubRepositoryModel) -> GitHubRepository:
        return GitHubRepository(
            id=model.id,
            user_id=model.user_id,
            github_repo_id=model.github_repo_id,
            owner=model.owner,
            name=model.name,
            full_name=model.full_name,
            is_private=model.is_private,
            default_branch=model.default_branch,
            html_url=model.html_url,
            commit_read_enabled=model.commit_read_enabled,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
