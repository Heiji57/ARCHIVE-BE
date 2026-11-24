from typing import Literal, Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class StorageConfig(BaseSettings):
    """프로필 사진·내보내기 zip 저장소.

    `local`(기본 — 개발·테스트)은 `AuthConfig.avatar_dir`/`export_dir` 디렉토리,
    `s3` 는 S3 호환 객체 저장소(운영은 Cloudflare R2). 버킷은 둘로 나눈다 — 사진은 공개
    (자체 도메인 + CDN 캐시), 내보내기는 비공개(짧은 서명 URL 로만).
    """

    # 검증 오류에 입력(.env 전체가 들어온다)을 싣지 않는다 — 시작 실패 로그에 시크릿이 남지 않게.
    model_config = SettingsConfigDict(
        env_prefix="STORAGE_", env_file=".env", extra="ignore", hide_input_in_errors=True
    )

    backend: Literal["local", "s3"] = "local"
    # R2: https://<account_id>.r2.cloudflarestorage.com
    endpoint_url: str = ""
    region: str = "auto"  # R2 는 "auto"
    access_key_id: str = ""
    secret_access_key: SecretStr = SecretStr("")
    avatar_bucket: str = ""
    # 사진 버킷에 연결한 공개 도메인(예: https://cdn.example.com). r2.dev 주소는 요청 제한이
    # 있는 개발용이라 운영에 쓰지 않는다.
    avatar_public_url: str = ""
    export_bucket: str = ""

    @model_validator(mode="after")
    def _require_s3_fields(self) -> Self:
        if self.backend != "s3":
            return self
        missing = [
            f"STORAGE_{name.upper()}"
            for name in (
                "endpoint_url",
                "access_key_id",
                "avatar_bucket",
                "avatar_public_url",
                "export_bucket",
            )
            if not getattr(self, name)
        ]
        if not self.secret_access_key.get_secret_value():
            missing.append("STORAGE_SECRET_ACCESS_KEY")
        if missing:
            raise ValueError(f"STORAGE_BACKEND=s3 needs {', '.join(missing)}")
        return self
