"""내보내기 파일 저장 — `ExportStorage` 포트 구현. 어느 쪽이든 공개 경로가 아니다.

- `local`(개발·테스트): 비공개 디렉토리(`EXPORT_DIR`, 기본 exports/). API 가 파일을 직접 보낸다.
- `s3`(운영, Cloudflare R2): 비공개 내보내기 버킷. 내려받기는 5분짜리 서명 URL 로 리다이렉트
  (`Content-Disposition: attachment`). 7일 뒤 `worker.purge_exports` 가 지우고, 버킷 수명 규칙이
  한 번 더 막는다.

어느 쪽이든 서명 토큰이 붙은 `GET /exports/{id}/download` 를 거쳐야 받는다.
`make_export_storage(settings)` 로 고른다(API DI·워커 같은 곳).
"""

import asyncio
import os
import shutil
from pathlib import Path
from typing import Any

from app.data.application.ports import ExportFile, ExportStorage
from app.shared.domain.exceptions.external import StorageUnavailableException
from app.shared.infrastructure.config.settings import AppConfig
from app.shared.infrastructure.storage import s3

# 리다이렉트를 바로 따라가므로 짧게 — 새어 나가도 오래 쓰이지 않게.
DOWNLOAD_URL_TTL_SECONDS = 300
_CONTENT_TYPE = "application/zip"


class LocalExportStorage:
    def __init__(self, directory: str) -> None:
        self._dir = Path(directory)

    async def save(self, key: str, source: Path) -> None:
        try:
            await asyncio.to_thread(self._save, self._path(key), source)
        except OSError as e:
            raise StorageUnavailableException(f"{type(e).__name__}: {e}") from e

    def _save(self, target: Path, source: Path) -> None:
        # 다른 파일시스템이면 move 가 복사라 중간에 실패할 수 있다 — 같은 디렉토리의 임시 이름에
        # 다 옮긴 뒤 이름만 바꿔(원자적), 반쯤 쓴 파일이 키 이름으로 남지 않게 한다.
        self._dir.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(f".{target.name}.partial")
        try:
            shutil.move(source, partial)
            os.replace(partial, target)
        except OSError:
            partial.unlink(missing_ok=True)
            raise

    async def remove(self, key: str) -> None:
        try:
            await asyncio.to_thread(self._path(key).unlink, missing_ok=True)
        except OSError as e:
            raise StorageUnavailableException(f"{type(e).__name__}: {e}") from e

    async def locate(self, key: str, filename: str) -> ExportFile | None:
        path = self._path(key)
        try:
            found = await asyncio.to_thread(path.is_file)
        except OSError as e:
            raise StorageUnavailableException(f"{type(e).__name__}: {e}") from e
        return ExportFile(path=path) if found else None

    def _path(self, key: str) -> Path:
        return self._dir / Path(key).name  # 경로 탈출 방지


class S3ExportStorage:
    def __init__(self, client: Any, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    async def save(self, key: str, source: Path) -> None:
        # upload_file 은 큰 파일을 알아서 나눠 올린다(multipart).
        await s3.call(
            self._client.upload_file,
            str(source),
            self._bucket,
            key,
            ExtraArgs={"ContentType": _CONTENT_TYPE},
        )

    async def remove(self, key: str) -> None:
        await s3.call(self._client.delete_object, Bucket=self._bucket, Key=key)  # 없어도 성공

    async def locate(self, key: str, filename: str) -> ExportFile | None:
        if not await s3.exists(self._client, self._bucket, key):
            return None
        url: str = await s3.call(
            self._client.generate_presigned_url,
            "get_object",
            Params={
                "Bucket": self._bucket,
                "Key": key,
                "ResponseContentType": _CONTENT_TYPE,
                "ResponseContentDisposition": f'attachment; filename="{filename}"',
            },
            ExpiresIn=DOWNLOAD_URL_TTL_SECONDS,
        )
        return ExportFile(url=url)


def make_export_storage(settings: AppConfig) -> ExportStorage:
    if settings.storage.backend == "s3":
        return S3ExportStorage(s3.get_s3_client(settings.storage), settings.storage.export_bucket)
    return LocalExportStorage(settings.auth.export_dir)
