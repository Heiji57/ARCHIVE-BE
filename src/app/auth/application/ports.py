"""auth 응용 계층이 바깥(파일 저장소·Redis·외부 토큰 철회)을 쓰는 좁은 포트."""

from dataclasses import dataclass
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


class ExternalTokenRevoker(Protocol):
    async def enqueue(self, tokens: list[ExternalToken]) -> None:
        """GitHub·Google 토큰 철회를 작업으로 넘긴다(커밋 뒤에 부른다). 실패하면 3번 다시."""
        ...
