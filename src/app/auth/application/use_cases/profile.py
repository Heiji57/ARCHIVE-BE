"""프로필 이름과 사진(01 §2)."""

import asyncio
import secrets
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from app.auth.application.ports import AvatarStorage
from app.auth.domain.exceptions.exceptions import (
    AvatarTooLargeException,
    AvatarUnsupportedTypeException,
)
from app.shared.domain.utils.unset import UNSET, _Unset
from app.user.domain.exceptions.exceptions import UserNotFoundException
from app.user.domain.models.user import User
from app.user.domain.repositories.repository import IUserRepository

AVATAR_MAX_BYTES = 2 * 1024 * 1024
AVATAR_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})


@dataclass(frozen=True)
class UpdateProfileCommand:
    user_id: str
    display_name: str | None | _Unset = UNSET  # 생략=그대로, None=지움


class UpdateProfileUseCase:
    def __init__(self, user_repo: IUserRepository) -> None:
        self._user_repo = user_repo

    async def execute(self, cmd: UpdateProfileCommand) -> User:
        user = await _user(self._user_repo, cmd.user_id)
        if isinstance(cmd.display_name, _Unset):
            return user
        updated = replace(user, display_name=cmd.display_name, updated_at=datetime.now(UTC))
        return await self._user_repo.save(updated)


class UploadAvatarUseCase:
    def __init__(self, user_repo: IUserRepository, storage: AvatarStorage) -> None:
        self._user_repo = user_repo
        self._storage = storage

    async def execute(self, user_id: str, content_type: str | None, raw: bytes) -> User:
        if content_type not in AVATAR_TYPES:
            raise AvatarUnsupportedTypeException()
        if len(raw) > AVATAR_MAX_BYTES:
            raise AvatarTooLargeException()
        user = await _user(self._user_repo, user_id)
        # 디코드·줄이기·인코드는 CPU 작업 — 이벤트 루프를 막지 않게 스레드로.
        data = await asyncio.to_thread(self._storage.prepare, raw)
        # 키에 사용자 id 를 넣지 않는다 — 사진 URL 로 사용자를 알 수 없게.
        key = f"{secrets.token_urlsafe(18)}.webp"
        await self._storage.put(key, data)
        saved = await self._user_repo.save(
            replace(user, avatar_key=key, updated_at=datetime.now(UTC))
        )
        if user.avatar_key:
            await self._storage.remove(user.avatar_key)
        return saved


class DeleteAvatarUseCase:
    def __init__(self, user_repo: IUserRepository, storage: AvatarStorage) -> None:
        self._user_repo = user_repo
        self._storage = storage

    async def execute(self, user_id: str) -> User:
        user = await _user(self._user_repo, user_id)
        if not user.avatar_key:
            return user
        saved = await self._user_repo.save(
            replace(user, avatar_key=None, updated_at=datetime.now(UTC))
        )
        await self._storage.remove(user.avatar_key)
        return saved


async def _user(repo: IUserRepository, user_id: str) -> User:
    user = await repo.find_by_id(user_id)
    if user is None:
        raise UserNotFoundException()
    return user
