"""auth 응용 계층이 바깥(파일 저장소·Redis·외부 토큰 철회)을 쓰는 좁은 포트."""

from dataclasses import dataclass, field
from typing import Protocol


class AvatarStorage(Protocol):
    def prepare(self, raw: bytes) -> bytes:
        """이미지를 검사해 256px 정사각형으로 줄인 저장용 바이트. 이미지가 아니면
        AvatarUnsupportedTypeException."""
        ...

    async def put(self, key: str, data: bytes) -> None: ...

    async def remove(self, key: str) -> None:
        """없어도 오류가 아니다."""
        ...


class DeletedAccountMarker(Protocol):
    async def mark(self, user_id: str) -> None:
        """남은 access token 을 막는 표식(access token 수명만큼)."""
        ...


@dataclass(frozen=True)
class ExternalToken:
    provider: str  # github | google
    token: str


@dataclass(frozen=True)
class DeletedAccount:
    """계정 삭제 트랜잭션이 끝낸 뒤 마무리할 것."""

    user_id: str
    avatar_key: str | None = None
    tokens: list[ExternalToken] = field(default_factory=list)


class AccountDeletionDispatcher(Protocol):
    async def dispatch(self, deleted: DeletedAccount) -> None:
        """마무리(세션 폐기·토큰 표식·사진 파일·외부 토큰 철회)를 작업으로 넘긴다.

        요청 커밋보다 먼저 불릴 수 있다 — 작업이 `users.deleted_at` 이 커밋된 것을 확인한 뒤에만
        실행하고, 롤백됐으면 아무것도 하지 않는다.
        """
        ...
