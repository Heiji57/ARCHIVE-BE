"""data 모듈이 바깥(파일 저장소)을 쓰는 좁은 포트."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ExportFile:
    """내려받을 곳 — 로컬은 파일 경로(API 가 직접 보낸다), 객체 저장소는 짧은 서명 URL."""

    path: Path | None = None
    url: str | None = None


class ExportStorage(Protocol):
    async def save(self, key: str, source: Path) -> None:
        """다 만든 zip(source)을 key 로 넣는다. source 는 호출한 쪽이 치운다."""
        ...

    async def remove(self, key: str) -> None:
        """없어도 오류가 아니다."""
        ...

    async def locate(self, key: str, filename: str) -> ExportFile | None:
        """내려받을 곳. 파일이 없으면 None."""
        ...
