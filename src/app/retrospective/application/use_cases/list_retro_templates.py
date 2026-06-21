from app.retrospective.domain.models.retro_template import RetroTemplate
from app.retrospective.domain.models.value_objects import RetroType
from app.retrospective.domain.repositories.repository import IRetroTemplateRepository


class ListRetroTemplatesUseCase:
    def __init__(self, repo: IRetroTemplateRepository) -> None:
        self._repo = repo

    async def execute(
        self, user_id: str, retro_type: RetroType | None = None
    ) -> list[RetroTemplate]:
        if retro_type is not None:
            return await self._repo.find_by_user_and_type(user_id, retro_type)
        return await self._repo.find_by_user(user_id)
