from app.user.domain.exceptions.exceptions import UserNotFoundException
from app.user.domain.models.user import User
from app.user.domain.repositories.repository import IUserRepository


class GetMeUseCase:
    def __init__(self, user_repo: IUserRepository) -> None:
        self._user_repo = user_repo

    async def execute(self, user_id: str) -> User:
        user = await self._user_repo.find_by_id(user_id)
        if not user:
            raise UserNotFoundException()
        return user
