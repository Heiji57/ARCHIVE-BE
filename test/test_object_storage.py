"""파일 저장소 — S3 호환(R2)은 botocore Stubber 로 요청 모양을, 로컬은 실제 파일로 본다."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from botocore.stub import ANY, Stubber
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import ValidationError

from app.auth.infrastructure.storage.avatar_storage import (
    S3AvatarStorage,
    avatar_public_base,
    avatar_url,
)
from app.data.application.ports import ExportFile
from app.data.application.use_cases.exports import ExportDownload
from app.data.domain.exceptions.exceptions import ExportNotFoundException
from app.data.domain.models.export import ExportJob
from app.data.infrastructure.export.storage import LocalExportStorage, S3ExportStorage
from app.data.presentation.export_router import download_export
from app.shared.domain.exceptions.external import StorageUnavailableException
from app.shared.infrastructure.auth.jwt import create_export_download_token
from app.shared.infrastructure.config.settings import AppConfig
from app.shared.infrastructure.config.storage import StorageConfig
from app.shared.infrastructure.storage.s3 import make_s3_client

_S3 = {
    "backend": "s3",
    "endpoint_url": "https://acct.r2.cloudflarestorage.com",
    "access_key_id": "test-key",
    "secret_access_key": "test-secret",
    "avatar_bucket": "avatars",
    "avatar_public_url": "https://cdn.example.com/",
    "export_bucket": "exports",
}


@pytest.fixture
def client() -> Any:
    return make_s3_client(StorageConfig(**_S3))  # type: ignore[arg-type]


# ── 설정 ──────────────────────────────────────────────────────────────────


def test_s3_backend_requires_all_fields() -> None:
    with pytest.raises(ValidationError, match="STORAGE_EXPORT_BUCKET"):
        StorageConfig(**{**_S3, "export_bucket": ""})  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="STORAGE_SECRET_ACCESS_KEY"):
        StorageConfig(**{**_S3, "secret_access_key": ""})  # type: ignore[arg-type]
    assert StorageConfig(backend="local").backend == "local"  # 로컬은 아무것도 필요 없다


def test_production_refuses_local_files() -> None:
    # 운영 compose 는 볼륨이 없다 — 로컬 파일이면 조용히 깨지므로 시작할 때 막는다.
    with pytest.raises(ValidationError, match="STORAGE_BACKEND=s3"):
        AppConfig(app_env="production", storage=StorageConfig(backend="local"))
    ok = AppConfig(app_env="production", storage=StorageConfig(**_S3))  # type: ignore[arg-type]
    assert ok.storage.backend == "s3"


def test_avatar_url_follows_backend() -> None:
    s3 = AppConfig(storage=StorageConfig(**_S3))  # type: ignore[arg-type]
    local = AppConfig(storage=StorageConfig(backend="local"))
    assert avatar_url(avatar_public_base(s3), "k.webp") == "https://cdn.example.com/k.webp"
    assert avatar_url(avatar_public_base(local), "k.webp") == "/static/avatars/k.webp"
    assert avatar_url(avatar_public_base(s3), None) is None


# ── 프로필 사진(S3) ───────────────────────────────────────────────────────


async def test_s3_avatar_put_is_public_cacheable_webp(client: Any) -> None:
    storage = S3AvatarStorage(client, "avatars")
    with Stubber(client) as stub:
        stub.add_response(
            "put_object",
            {},
            {
                "Bucket": "avatars",
                "Key": "abc.webp",
                "Body": b"img",
                "ContentType": "image/webp",
                "CacheControl": "public, max-age=31536000, immutable",
            },
        )
        stub.add_response("delete_object", {}, {"Bucket": "avatars", "Key": "abc.webp"})
        await storage.put("abc.webp", b"img")
        await storage.remove("abc.webp")
        stub.assert_no_pending_responses()


async def test_s3_avatar_stale_keys_reads_every_page(client: Any) -> None:
    storage = S3AvatarStorage(client, "avatars")
    old = datetime.now(UTC) - timedelta(days=2)
    new = datetime.now(UTC)
    with Stubber(client) as stub:
        stub.add_response(
            "list_objects_v2",
            {
                "Contents": [
                    {"Key": "old1.webp", "LastModified": old},
                    {"Key": "new.webp", "LastModified": new},
                ],
                "IsTruncated": True,
                "NextContinuationToken": "t2",
            },
            {"Bucket": "avatars"},
        )
        stub.add_response(
            "list_objects_v2",
            {"Contents": [{"Key": "old2.webp", "LastModified": old}], "IsTruncated": False},
            {"Bucket": "avatars", "ContinuationToken": "t2"},
        )
        assert await storage.stale_keys(86400) == ["old1.webp", "old2.webp"]
        stub.assert_no_pending_responses()


async def test_s3_errors_become_storage_unavailable(client: Any) -> None:
    storage = S3AvatarStorage(client, "avatars")
    with Stubber(client) as stub:
        stub.add_client_error("put_object", service_error_code="AccessDenied", http_status_code=403)
        with pytest.raises(StorageUnavailableException):
            await storage.put("abc.webp", b"img")


# ── 내보내기(S3) ──────────────────────────────────────────────────────────


async def test_s3_export_save_uploads_zip(client: Any, tmp_path: Path) -> None:
    source = tmp_path / "exp_1.zip"
    source.write_bytes(b"PK zip")
    with Stubber(client) as stub:
        stub.add_response(
            "put_object",
            {},
            {
                "Bucket": "exports",
                "Key": "exp_1.zip",
                "Body": ANY,
                "ContentType": "application/zip",
            },
        )
        await S3ExportStorage(client, "exports").save("exp_1.zip", source)
        stub.assert_no_pending_responses()


async def test_s3_export_locate_gives_short_attachment_url(client: Any) -> None:
    storage = S3ExportStorage(client, "exports")
    with Stubber(client) as stub:
        stub.add_response("head_object", {}, {"Bucket": "exports", "Key": "exp_1.zip"})
        stub.add_client_error("head_object", service_error_code="404", http_status_code=404)
        found = await storage.locate("exp_1.zip", "archive-export-2026-11-24.zip")
        assert await storage.locate("gone.zip", "x.zip") is None  # 없으면 None(→ 404)
    assert found is not None and found.url is not None and found.path is None
    url = urlparse(found.url)
    query = parse_qs(url.query)
    assert url.netloc == "acct.r2.cloudflarestorage.com" and url.path == "/exports/exp_1.zip"
    assert query["X-Amz-Expires"] == ["300"]
    assert query["response-content-disposition"] == [
        'attachment; filename="archive-export-2026-11-24.zip"'
    ]


# ── 내보내기(로컬) ────────────────────────────────────────────────────────


async def test_local_export_save_locate_remove(tmp_path: Path) -> None:
    storage = LocalExportStorage(str(tmp_path / "exports"))
    built = tmp_path / "build" / "exp_1.zip"
    built.parent.mkdir()
    built.write_bytes(b"PK zip")
    await storage.save("exp_1.zip", built)
    found = await storage.locate("../exp_1.zip", "x.zip")  # 경로 탈출은 이름만 남긴다
    assert found == ExportFile(path=tmp_path / "exports" / "exp_1.zip")
    assert found.path is not None and found.path.read_bytes() == b"PK zip"
    await storage.remove("exp_1.zip")
    await storage.remove("exp_1.zip")  # 없어도 오류가 아니다
    assert await storage.locate("exp_1.zip", "x.zip") is None


async def test_local_export_save_leaves_nothing_when_move_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.data.infrastructure.export.storage as mod

    def broken_move(src: Path, dst: Path) -> None:
        Path(dst).write_bytes(b"PK half")  # 다른 파일시스템 복사 도중 디스크가 참
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(mod.shutil, "move", broken_move)
    built = tmp_path / "exp_1.zip"
    built.write_bytes(b"PK zip")
    storage = LocalExportStorage(str(tmp_path / "exports"))
    with pytest.raises(StorageUnavailableException):
        await storage.save("exp_1.zip", built)
    assert list((tmp_path / "exports").iterdir()) == []  # 반쯤 쓴 파일이 남지 않는다


# ── 내려받기 응답 ─────────────────────────────────────────────────────────


class _Jobs:
    def __init__(self, job: ExportJob) -> None:
        self.job = job

    async def execute_by_id(self, export_id: str, now: datetime | None = None) -> ExportDownload:
        return ExportDownload(self.job, date(2026, 11, 25))  # 사용자 tz 날짜


class _Storage:
    def __init__(self, found: ExportFile | None) -> None:
        self.found = found
        self.asked: list[tuple[str, str]] = []

    async def locate(self, key: str, filename: str) -> ExportFile | None:
        self.asked.append((key, filename))
        return self.found


def _job(file_key: str | None = "exp_1.zip") -> ExportJob:
    return ExportJob(
        id="exp_1",
        user_id="usr_1",
        scopes=["retro"],
        format="md",
        status="ready",
        created_at=datetime(2026, 11, 24, tzinfo=UTC),
        file_key=file_key,
    )


async def _download(job: ExportJob, storage: _Storage) -> Any:
    token = create_export_download_token("exp_1", timedelta(hours=1))
    return await download_export(
        "exp_1", use_case=_Jobs(job), storage=storage, token=token  # type: ignore[arg-type]
    )


async def test_download_redirects_to_object_storage(tmp_path: Path) -> None:
    storage = _Storage(ExportFile(url="https://acct.r2.cloudflarestorage.com/exports/x?sig"))
    resp = await _download(_job(), storage)
    assert isinstance(resp, RedirectResponse) and resp.status_code == 307
    assert resp.headers["location"] == "https://acct.r2.cloudflarestorage.com/exports/x?sig"
    # 파일 이름은 created_at(UTC 11-24)이 아니라 사용자 tz 날짜
    assert storage.asked == [("exp_1.zip", "archive-export-2026-11-25.zip")]


async def test_download_sends_local_file_or_404(tmp_path: Path) -> None:
    path = tmp_path / "exp_1.zip"
    path.write_bytes(b"PK")
    resp = await _download(_job(), _Storage(ExportFile(path=path)))
    assert isinstance(resp, FileResponse) and resp.media_type == "application/zip"
    with pytest.raises(ExportNotFoundException):
        await _download(_job(), _Storage(None))
    with pytest.raises(ExportNotFoundException):
        await _download(_job(file_key=None), _Storage(ExportFile(path=path)))
