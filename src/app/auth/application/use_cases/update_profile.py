from dataclasses import dataclass

from app.user.domain.exceptions.exceptions import UserNotFoundException
from app.user.domain.models.user import User
from app.user.domain.repositories.repository import IUserRepository


@dataclass(frozen=True)
class UpdateProfileCommand:
    user_id: str
    display_name: str | None = None


class UpdateProfileUseCase:
    def __init__(self, user_repo: IUserRepository) -> None:
        self._user_repo = user_repo

    async def execute(self, cmd: UpdateProfileCommand) -> User:
        user = await self._user_repo.find_by_id(cmd.user_id)
        if not user:
            raise UserNotFoundException()
        # 현재 User 엔티티에 display_name 필드가 없으므로 저장만 반환
        # Phase 2에서 User 도메인에 display_name 추가 시 확장
        saved = await self._user_repo.save(user)
        return saved
