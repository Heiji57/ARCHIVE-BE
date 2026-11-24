"""S3 호환 객체 저장소 클라이언트 — 운영은 Cloudflare R2(`STORAGE_BACKEND=s3`).

boto3 는 동기 라이브러리라 `asyncio.to_thread` 로 부른다. 클라이언트는 스레드 안전해서 프로세스에
하나만 만든다(`get_s3_client`). 라이브러리 예외는 여기서 `StorageUnavailableException` 으로 바꾼다.
"""

import asyncio
from collections.abc import Callable
from functools import lru_cache
from typing import Any

import boto3
from boto3.exceptions import Boto3Error
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.shared.domain.exceptions.external import StorageUnavailableException
from app.shared.infrastructure.config.settings import get_settings
from app.shared.infrastructure.config.storage import StorageConfig

_NOT_FOUND = {"404", "NoSuchKey", "NotFound"}


def make_s3_client(cfg: StorageConfig) -> Any:
    return boto3.session.Session().client(
        "s3",
        endpoint_url=cfg.endpoint_url or None,
        region_name=cfg.region,
        aws_access_key_id=cfg.access_key_id,
        aws_secret_access_key=cfg.secret_access_key.get_secret_value(),
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            connect_timeout=5,
            read_timeout=60,
            retries={"max_attempts": 3, "mode": "standard"},
            # boto3 1.36+ 의 기본 체크섬 헤더를 모든 S3 호환 저장소가 받지는 않는다 — 필요할 때만.
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )


@lru_cache(maxsize=1)
def get_s3_client() -> Any:
    return make_s3_client(get_settings().storage)


def _translate(e: Exception) -> StorageUnavailableException:
    translated = StorageUnavailableException(f"{type(e).__name__}: {e}")
    translated.__cause__ = e
    return translated


async def call(fn: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
    try:
        return await asyncio.to_thread(fn, *args, **kwargs)
    except (BotoCoreError, ClientError, Boto3Error, OSError) as e:
        # Boto3Error: upload_file 의 S3UploadFailedError, OSError: 올릴 파일을 못 읽음
        raise _translate(e) from e


async def exists(client: Any, bucket: str, key: str) -> bool:
    try:
        await asyncio.to_thread(client.head_object, Bucket=bucket, Key=key)
    except ClientError as e:
        if str(e.response.get("Error", {}).get("Code")) in _NOT_FOUND:
            return False
        raise _translate(e) from e
    except BotoCoreError as e:
        raise _translate(e) from e
    return True


def list_keys_older_than(client: Any, bucket: str, cutoff_epoch: float) -> list[str]:
    """버킷 전체에서 마지막 수정이 cutoff 보다 이른 키(동기 — to_thread 안에서 부른다).

    버킷 전체를 훑으므로 사진 버킷에는 사진 말고 다른 것을 두지 않는다(고아 정리가 지운다).
    """
    keys: list[str] = []
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            if obj["LastModified"].timestamp() < cutoff_epoch:
                keys.append(obj["Key"])
    return keys
