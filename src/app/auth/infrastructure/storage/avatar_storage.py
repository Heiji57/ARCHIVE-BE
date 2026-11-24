"""프로필 사진 저장 — 256px webp. 키는 임의 값이라 URL 로 사용자를 알 수 없다.

- `local`(개발·테스트): `AVATAR_DIR`(기본 static/avatars), `/static` 마운트로 바로 서빙.
- `s3`(운영, Cloudflare R2): 공개 사진 버킷. 자체 도메인(`STORAGE_AVATAR_PUBLIC_URL`)으로 서빙하고
  1시간 캐시한다 — 대부분 CDN 캐시에서 응답하면서, 지운 사진이 오래 남지 않게.

어느 쪽이든 `make_avatar_storage(settings)` 로 고른다(API DI·워커 같은 곳).
"""

import asyncio
import io
import time
from pathlib import Path
from typing import Any, Protocol

from PIL import Image, ImageOps, UnidentifiedImageError

from app.auth.application.ports import AvatarStorage
from app.auth.domain.exceptions.exceptions import AvatarUnsupportedTypeException
from app.shared.domain.exceptions.external import StorageUnavailableException
from app.shared.infrastructure.config.settings import AppConfig
from app.shared.infrastructure.storage import s3

AVATAR_SIZE = 256
_FORMATS = {"PNG", "JPEG", "WEBP"}
# 압축 폭탄 방지 — 2MB 안에 큰 픽셀 수를 담은 파일을 펼치지 않는다(16MP ≈ RGBA 64MB).
_MAX_PIXELS = 16_000_000
# 짧게 — CDN 엣지 캐시는 객체를 지워도 남는다. 계정 삭제·사진 바꾸기 뒤 옛 사진이 길어야 1시간만
# 보이게(키가 임의 값이라 내용은 안 바뀌지만 immutable·장기 캐시는 '바로 내린다'를 깬다).
_CACHE_CONTROL = "public, max-age=3600"


def prepare_avatar(raw: bytes) -> bytes:
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


class SweepableAvatarStorage(AvatarStorage, Protocol):
    async def stale_keys(self, older_than_seconds: float) -> list[str]:
        """만든 지 older_than 이 지난 키 — 고아 정리 후보(방금 올린 파일은 건드리지 않게)."""
        ...


class LocalAvatarStorage:
    def __init__(self, directory: str) -> None:
        self._dir = Path(directory)

    def prepare(self, raw: bytes) -> bytes:
        return prepare_avatar(raw)

    async def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        try:
            await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
            await asyncio.to_thread(path.write_bytes, data)
        except OSError as e:
            raise StorageUnavailableException(f"{type(e).__name__}: {e}") from e

    async def remove(self, key: str) -> None:
        try:
            await asyncio.to_thread(self._path(key).unlink, missing_ok=True)
        except OSError as e:
            raise StorageUnavailableException(f"{type(e).__name__}: {e}") from e

    async def stale_keys(self, older_than_seconds: float) -> list[str]:
        try:
            return await asyncio.to_thread(self._stale_keys, time.time() - older_than_seconds)
        except OSError as e:
            raise StorageUnavailableException(f"{type(e).__name__}: {e}") from e

    def _stale_keys(self, cutoff: float) -> list[str]:
        if not self._dir.is_dir():
            return []
        return [p.name for p in self._dir.iterdir() if p.is_file() and p.stat().st_mtime < cutoff]

    def _path(self, key: str) -> Path:
        # 키는 서버가 만든 값이지만 경로 탈출은 한 번 더 막는다.
        return self._dir / Path(key).name


class S3AvatarStorage:
    def __init__(self, client: Any, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    def prepare(self, raw: bytes) -> bytes:
        return prepare_avatar(raw)

    async def put(self, key: str, data: bytes) -> None:
        await s3.call(
            self._client.put_object,
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType="image/webp",
            CacheControl=_CACHE_CONTROL,
        )

    async def remove(self, key: str) -> None:
        await s3.call(self._client.delete_object, Bucket=self._bucket, Key=key)  # 없어도 성공

    async def stale_keys(self, older_than_seconds: float) -> list[str]:
        keys: list[str] = await s3.call(
            s3.list_keys_older_than, self._client, self._bucket, time.time() - older_than_seconds
        )
        return keys


def make_avatar_storage(settings: AppConfig) -> SweepableAvatarStorage:
    if settings.storage.backend == "s3":
        return S3AvatarStorage(s3.get_s3_client(settings.storage), settings.storage.avatar_bucket)
    return LocalAvatarStorage(settings.auth.avatar_dir)


def avatar_public_base(settings: AppConfig) -> str:
    if settings.storage.backend == "s3":
        return settings.storage.avatar_public_url
    return settings.auth.avatar_public_path


def avatar_url(public_base: str, key: str | None) -> str | None:
    return f"{public_base.rstrip('/')}/{key}" if key else None
