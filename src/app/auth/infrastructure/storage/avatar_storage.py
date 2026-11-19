"""프로필 사진 저장 — 로컬 디렉토리(`AVATAR_DIR`, 기본 static/avatars)에 webp 로.

`/static` 마운트로 바로 서빙된다. 키는 임의 값이라 URL 로 사용자를 알 수 없다.
운영에서 객체 저장소(S3 호환)로 옮길 때는 이 AvatarStorage 구현만 바꾼다.
"""

import asyncio
import io
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from app.auth.domain.exceptions.exceptions import AvatarUnsupportedTypeException

AVATAR_SIZE = 256
_FORMATS = {"PNG", "JPEG", "WEBP"}
# 압축 폭탄 방지 — 2MB 안에 큰 픽셀 수를 담은 파일을 펼치지 않는다(16MP ≈ RGBA 64MB).
_MAX_PIXELS = 16_000_000


class LocalAvatarStorage:
    def __init__(self, directory: str) -> None:
        self._dir = Path(directory)

    def prepare(self, raw: bytes) -> bytes:
        try:
            with Image.open(io.BytesIO(raw)) as source:
                if source.format not in _FORMATS or source.width * source.height > _MAX_PIXELS:
                    raise AvatarUnsupportedTypeException()
                upright = ImageOps.exif_transpose(source)
                square = ImageOps.fit(upright.convert("RGBA"), (AVATAR_SIZE, AVATAR_SIZE))
                out = io.BytesIO()
                square.save(out, format="WEBP", quality=85)
                return out.getvalue()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as e:
            raise AvatarUnsupportedTypeException() from e

    async def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)

    async def remove(self, key: str) -> None:
        await asyncio.to_thread(self._path(key).unlink, missing_ok=True)

    def _path(self, key: str) -> Path:
        # 키는 서버가 만든 값이지만 경로 탈출은 한 번 더 막는다.
        return self._dir / Path(key).name


def avatar_url(public_path: str, key: str | None) -> str | None:
    return f"{public_path.rstrip('/')}/{key}" if key else None
