"""01 §2 프로필 이름·사진, 01 §3 계정 soft delete."""

import io
import os
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from PIL import Image
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.shared.infrastructure.database.models  # noqa: F401  (FK 대상 테이블 등록)
from app.auth.application.use_cases.delete_account import (
    DeleteAccountUseCase,
    FinishAccountDeletionUseCase,
)
from app.auth.application.use_cases.profile import (
    AVATAR_MAX_BYTES,
    DeleteAvatarUseCase,
    UpdateProfileCommand,
    UpdateProfileUseCase,
    UploadAvatarUseCase,
)
from app.auth.domain.exceptions.exceptions import (
    AccountDeleteConfirmMismatchException,
    AvatarTooLargeException,
    AvatarUnsupportedTypeException,
    ReauthRequiredException,
)
from app.auth.domain.models.value_objects import OAuthProvider, TokenType
from app.auth.infrastructure.storage.avatar_storage import LocalAvatarStorage
from app.auth.presentation.requests.requests import UpdateProfileRequest
from app.shared.domain.context.user_context import UserContext
from app.shared.infrastructure.auth.jwt import _decode, create_access_token
from app.user.domain.models.user import User
from app.user.domain.models.value_objects import Email
from app.user.infrastructure.persistence.repositories.user_repo import UserRepository

_NOW = datetime(2026, 11, 17, tzinfo=UTC)


def _user(**kw) -> User:
    base = dict(
        id="usr_p",
        email=Email("me@example.com"),
        password_hash=None,
        country="KR",
        region=None,
        timezone="Asia/Seoul",
        created_at=_NOW,
    )
    base.update(kw)
    return User(**base)


class _Users:
    def __init__(self, user: User) -> None:
        self.user = user
        self.soft_deleted: list[str] = []

    async def find_by_id(self, id):
        return self.user if self.user.id == id else None

    async def save(self, user):
        self.user = user
        return user

    async def soft_delete(self, id):
        self.soft_deleted.append(id)


def _png(w=600, h=400) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (w, h), (200, 10, 10)).save(out, format="PNG")
    return out.getvalue()


# ── 이름 ──────────────────────────────────────────────────────────────────


async def test_display_name_omit_keeps_null_clears_and_set():
    users = _Users(_user(display_name="민수"))
    uc = UpdateProfileUseCase(users)  # type: ignore[arg-type]
    assert (await uc.execute(UpdateProfileCommand(user_id="usr_p"))).display_name == "민수"
    assert (await uc.execute(UpdateProfileCommand("usr_p", None))).display_name is None
    assert (await uc.execute(UpdateProfileCommand("usr_p", "새 이름"))).display_name == "새 이름"


def test_display_name_validation_strips_and_bounds():
    assert UpdateProfileRequest.model_validate({"displayName": "  a  "}).display_name == "a"
    for bad in ("   ", "x" * 51):
        with pytest.raises(ValidationError):
            UpdateProfileRequest.model_validate({"displayName": bad})


# ── 사진 ──────────────────────────────────────────────────────────────────


async def test_avatar_resized_to_256_webp_and_old_files_left_for_sweep(tmp_path):
    storage = LocalAvatarStorage(str(tmp_path))
    users = _Users(_user())
    up = UploadAvatarUseCase(users, storage)  # type: ignore[arg-type]
    first = await up.execute("usr_p", "image/png", _png())
    assert first.avatar_key and "usr_p" not in first.avatar_key
    with Image.open(tmp_path / first.avatar_key) as img:
        assert (img.format, img.size) == ("WEBP", (256, 256))
    second = await up.execute("usr_p", "image/png", _png(100, 300))
    # 옛 파일은 요청에서 지우지 않는다(커밋 실패 때 링크가 깨지지 않게) — 고아 정리가 지운다
    assert (tmp_path / first.avatar_key).exists() and users.user.avatar_key == second.avatar_key
    gone = await DeleteAvatarUseCase(users).execute("usr_p")  # type: ignore[arg-type]
    assert gone.avatar_key is None
    assert set(storage.stale_keys(-1)) == {first.avatar_key, second.avatar_key}
    assert storage.stale_keys(3600) == []  # 방금 만든 파일은 정리 대상이 아니다


async def test_avatar_rejects_type_size_and_non_image(tmp_path):
    up = UploadAvatarUseCase(_Users(_user()), LocalAvatarStorage(str(tmp_path)))  # type: ignore[arg-type]
    with pytest.raises(AvatarUnsupportedTypeException):
        await up.execute("usr_p", "image/gif", _png())
    with pytest.raises(AvatarTooLargeException):
        await up.execute("usr_p", "image/png", b"0" * (AVATAR_MAX_BYTES + 1))
    with pytest.raises(AvatarUnsupportedTypeException):
        await up.execute("usr_p", "image/png", b"not an image")


# ── 최근 로그인 시각(auth_time) ────────────────────────────────────────────


def test_access_token_carries_auth_time_through_refresh():
    login_at = time.time() - 3600
    ctx = _decode(create_access_token("usr_p", auth_time=login_at), TokenType.ACCESS)
    assert ctx.auth_time == int(login_at)


# ── 계정 삭제 ──────────────────────────────────────────────────────────────


class _Sessions:
    def __init__(self) -> None:
        self.revoked: list[str] = []

    async def revoke_all(self, user_id):
        self.revoked.append(user_id)


class _OAuth:
    def __init__(self) -> None:
        self.rows = [
            SimpleNamespace(id="oc1", provider=OAuthProvider.GITHUB, access_token="gh_tok")
        ]

    async def find_by_user_id(self, user_id):
        return list(self.rows)

    async def delete(self, id):
        self.rows = [r for r in self.rows if r.id != id]


class _Cal:
    def __init__(self) -> None:
        self.conn = SimpleNamespace(refresh_token="g_refresh")

    async def find_by_user_id(self, user_id):
        return self.conn

    async def delete_by_user_id(self, user_id):
        self.conn = None


class _Marker:
    def __init__(self) -> None:
        self.marked: list[str] = []

    async def mark(self, user_id):
        self.marked.append(user_id)


def _delete_uc(users):
    parts = SimpleNamespace(oauth=_OAuth(), cal=_Cal())
    uc = DeleteAccountUseCase(users, parts.oauth, parts.cal)  # type: ignore[arg-type]
    return uc, parts


class _Storage:
    def __init__(self) -> None:
        self.removed: list[str] = []

    async def remove(self, key):
        self.removed.append(key)


async def test_delete_account_requires_recent_login_and_matching_confirm():
    users = _Users(_user(display_name="민수"))
    uc, _ = _delete_uc(users)
    now = time.time()
    for auth_time in (None, now - 601):
        with pytest.raises(ReauthRequiredException):
            await uc.execute(UserContext("usr_p", "", auth_time), "민수", now=now)
    with pytest.raises(AccountDeleteConfirmMismatchException):
        await uc.execute(UserContext("usr_p", "", now - 10), "다른 이름", now=now)
    with pytest.raises(AccountDeleteConfirmMismatchException):
        await uc.execute(UserContext("usr_p", "", now - 10), "   ", now=now)
    assert users.soft_deleted == []


async def test_delete_account_db_step_then_post_commit_lockout():
    users = _Users(_user(avatar_key="old.webp"))
    uc, parts = _delete_uc(users)
    now = time.time()
    deleted = await uc.execute(UserContext("usr_p", "", now - 10), "ME@example.com", now=now)
    # 트랜잭션 단계: 계정·연결·사진 키만
    assert users.soft_deleted == ["usr_p"] and users.user.avatar_key is None
    assert parts.oauth.rows == [] and parts.cal.conn is None
    assert {(t.provider, t.token) for t in deleted.tokens} == {
        ("github", "gh_tok"),
        ("google", "g_refresh"),
    }
    # 커밋 뒤 단계: 표식·세션·사진 파일·외부 토큰
    sessions, marker, storage = _Sessions(), _Marker(), _Storage()
    await FinishAccountDeletionUseCase(sessions, marker, storage).execute(  # type: ignore[arg-type]
        deleted.user_id, deleted.avatar_key
    )
    assert sessions.revoked == ["usr_p"] and marker.marked == ["usr_p"]
    assert storage.removed == ["old.webp"]


async def test_refresh_refuses_deleted_account():
    from app.auth.application.use_cases.refresh_token import RefreshTokenUseCase
    from app.auth.domain.exceptions.exceptions import RefreshTokenInvalidException

    class _Svc:
        revoked: list[str] = []

        async def rotate(self, raw, meta):
            return SimpleNamespace(
                refresh_token="r2", session_id="sess_1", user_id="usr_gone", issued_at=time.time()
            )

        async def revoke(self, session_id, user_id):
            self.revoked.append(session_id)

    svc = _Svc()
    with pytest.raises(RefreshTokenInvalidException):
        await RefreshTokenUseCase(svc, _Users(_user())).execute("sess_1.x", None)  # type: ignore[arg-type]
    assert svc.revoked == ["sess_1"]


async def test_get_current_user_rejects_deleted_marker(monkeypatch):
    from fastapi.security import HTTPAuthorizationCredentials

    from app.auth.domain.exceptions.exceptions import AuthTokenInvalidException
    from app.shared.infrastructure.auth import jwt as jwt_mod

    async def deleted(user_id):
        return user_id == "usr_gone"

    monkeypatch.setattr(jwt_mod, "is_account_deleted", deleted)
    creds = HTTPAuthorizationCredentials(
        scheme="Bearer", credentials=create_access_token("usr_gone")
    )
    with pytest.raises(AuthTokenInvalidException):
        await jwt_mod.get_current_user(creds)
    ok = HTTPAuthorizationCredentials(scheme="Bearer", credentials=create_access_token("usr_ok"))
    assert (await jwt_mod.get_current_user(ok)).id == "usr_ok"


# ── DB: 지운 계정은 없는 계정, 같은 이메일로 다시 가입, 30일 뒤 완전 삭제 ─────

_TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://ADMIN:heijiADMIN20090220!@localhost:5437/archive",
)
_IDS = ("usr_redesign_del_old", "usr_redesign_del_new", "usr_redesign_del_recent")


@pytest.fixture
async def factory():
    engine = create_async_engine(_TEST_DB_URL)
    f = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with f.begin() as s:
            col = await s.scalar(
                text(
                    "SELECT 1 FROM information_schema.columns"
                    " WHERE table_name='users' AND column_name='deleted_at'"
                )
            )
        if col is None:
            pytest.skip("TEST_DATABASE_URL 의 DB 가 최신 마이그레이션이 아니다")
    except OSError:
        pytest.skip("test DB unavailable")

    async def clean():
        async with f.begin() as s:
            for uid in _IDS:
                await s.execute(text("DELETE FROM topics WHERE user_id = :id"), {"id": uid})
                await s.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})

    await clean()
    yield f
    await clean()
    await engine.dispose()


async def test_deleted_account_is_gone_email_reusable_and_purged_after_30_days(factory):
    from app.user.infrastructure.persistence.account_purge import purge_unlinked_user_data
    from app.worker.tasks.account_cleanup import ACCOUNT_RETENTION

    email = "redesign-del@example.invalid"
    async with factory.begin() as s:
        repo = UserRepository(s)
        await repo.save(_user(id=_IDS[0], email=Email(email)))
        await repo.soft_delete(_IDS[0])
        assert await repo.find_by_id(_IDS[0]) is None
        assert await repo.find_by_email(email) is None
        # 같은 이메일로 새 가입 — 새 사용자 id
        await repo.save(_user(id=_IDS[1], email=Email(email)))
        assert (await repo.find_by_email(email)).id == _IDS[1]

        await repo.save(_user(id=_IDS[2], email=Email("redesign-del2@example.invalid")))
        await repo.soft_delete(_IDS[2])
        await s.execute(
            text("UPDATE users SET deleted_at = :t WHERE id = :id"),
            {"t": datetime.now(UTC) - timedelta(days=31), "id": _IDS[0]},
        )
        await s.execute(
            text("UPDATE users SET deleted_at = :t WHERE id = :id"),
            {"t": datetime.now(UTC) - timedelta(days=29), "id": _IDS[2]},
        )
        await s.execute(
            text(
                "INSERT INTO topics (id, user_id, name, created_at)"
                " VALUES ('top_del_old', :u, '주제', now())"
            ),
            {"u": _IDS[0]},
        )
        # 커밋된 deleted_at 이 보이는지(계정 삭제 마무리 작업의 확인), 사진 키는 지운 계정도 센다
        assert await repo.is_deleted(_IDS[0]) and not await repo.is_deleted(_IDS[1])
        await s.execute(
            text("UPDATE users SET avatar_key='kept.webp' WHERE id = :id"), {"id": _IDS[2]}
        )
        assert "kept.webp" in await repo.avatar_keys()
        due = await repo.find_deleted_before(datetime.now(UTC) - ACCOUNT_RETENTION)
        assert [u.id for u in due if u.id in _IDS] == [_IDS[0]]  # 29일째는 남는다
        await purge_unlinked_user_data(s, _IDS[0])
        await repo.purge(_IDS[0])
        left = await s.scalar(
            text("SELECT count(*) FROM users WHERE id = ANY(:ids)"), {"ids": list(_IDS)}
        )
        topics = await s.scalar(text("SELECT count(*) FROM topics WHERE id='top_del_old'"))
        assert (left, topics) == (2, 0)
