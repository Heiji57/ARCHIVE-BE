"""12 §2 내보내기 — 동시 하나·24시간 3번, zip 내용(휴지통 제외·폴더 구조·월별), 7일 뒤 410."""

import json
import os
import zipfile
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.shared.infrastructure.database.models  # noqa: F401  (FK 대상 테이블 등록)
from app.data.application.use_cases.exports import GetExportUseCase, RequestExportUseCase
from app.data.domain.exceptions.exceptions import (
    ExportDailyLimitException,
    ExportExpiredException,
    ExportInProgressException,
    ExportNotFoundException,
)
from app.data.domain.models.export import ExportJob
from app.data.infrastructure.export.builder import build_export
from app.data.infrastructure.persistence.repositories.export_repo import ExportRepository
from app.shared.infrastructure.auth.jwt import (
    create_export_download_token,
    decode_export_download_token,
)
from app.user.infrastructure.persistence.repositories.user_repo import UserRepository

_TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://ADMIN:heijiADMIN20090220!@localhost:5437/archive",
)
_U, _OTHER = "usr_redesign_export", "usr_redesign_export_b"


@pytest.fixture
async def factory():
    engine = create_async_engine(_TEST_DB_URL)
    f = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with f.begin() as s:
            if await s.scalar(text("SELECT to_regclass('public.exports')")) is None:
                pytest.skip("TEST_DATABASE_URL 의 DB 가 최신 마이그레이션이 아니다")
    except OSError:
        pytest.skip("test DB unavailable")
    async with f.begin() as s:
        for uid in (_U, _OTHER):
            await s.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
            await s.execute(
                text(
                    "INSERT INTO users (id, email, created_at, country, timezone)"
                    " VALUES (:id, :e, now(), 'KR', 'Asia/Seoul')"
                ),
                {"id": uid, "e": f"{uid}@example.invalid"},
            )
    yield f
    async with f.begin() as s:
        for uid in (_U, _OTHER):
            await s.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
    await engine.dispose()


async def test_one_at_a_time_and_three_per_day(factory):
    now = datetime.now(UTC)
    async with factory.begin() as s:
        uc = RequestExportUseCase(ExportRepository(s))
        first = await uc.execute(_U, ["retro"], "md", now=now)
        with pytest.raises(ExportInProgressException):
            await uc.execute(_U, ["todo"], "md", now=now)
        # 1시간 넘게 pending = 워커가 죽음 → 실패로 닫고 새 요청을 받는다
        second = await uc.execute(_U, ["todo"], "json", now=now + timedelta(hours=2))
        assert (await ExportRepository(s).get(first.id)).status == "failed"
        await ExportRepository(s).save(_ready(second, now))
        await uc.execute(_U, ["ai"], "md", now=now + timedelta(hours=2))
        await s.execute(text("UPDATE exports SET status='ready' WHERE user_id=:u"), {"u": _U})
        with pytest.raises(ExportDailyLimitException):
            await uc.execute(_U, ["ai"], "md", now=now + timedelta(hours=3))
        # 24시간이 지나면 다시
        later = await uc.execute(_U, ["ai"], "md", now=now + timedelta(hours=26))
        assert later.status == "pending"


def _ready(job: ExportJob, now: datetime) -> ExportJob:
    from dataclasses import replace

    return replace(
        job,
        status="ready",
        file_key=f"{job.id}.zip",
        ready_at=now,
        expires_at=now + timedelta(days=7),
    )


def test_download_date_is_users_local_day():
    from app.data.application.use_cases.exports import _local_date

    at = datetime(2026, 11, 24, 23, 30, tzinfo=UTC)  # 서울 11-25 08:30
    assert _local_date(at, "Asia/Seoul").isoformat() == "2026-11-25"
    assert _local_date(at, "Not/AZone").isoformat() == "2026-11-24"  # 잘못된 tz 는 UTC


async def test_get_is_owner_only_and_410_after_seven_days(factory):
    now = datetime.now(UTC)
    async with factory.begin() as s:
        job = await RequestExportUseCase(ExportRepository(s)).execute(_U, ["retro"], "md", now=now)
        await ExportRepository(s).save(_ready(job, now))
        get = GetExportUseCase(ExportRepository(s), UserRepository(s))
        assert (await get.execute(_U, job.id, now)).status == "ready"
        with pytest.raises(ExportNotFoundException):
            await get.execute(_OTHER, job.id, now)
        with pytest.raises(ExportExpiredException):
            await get.execute(_U, job.id, now + timedelta(days=7, seconds=1))
        download = await get.execute_by_id(job.id, now)
        assert download.job.id == job.id
        # 파일 이름 날짜는 사용자 tz(Asia/Seoul) 기준
        assert download.created_on == job.created_at.astimezone(ZoneInfo("Asia/Seoul")).date()
        # 지운 계정의 내려받기 링크는 막힌다
        await UserRepository(s).soft_delete(_U)
        with pytest.raises(ExportNotFoundException):
            await get.execute_by_id(job.id, now)
    token = create_export_download_token(job.id, timedelta(hours=24))
    assert decode_export_download_token(token) == job.id


async def test_zip_contents_follow_format_and_skip_trash(factory, tmp_path):
    async with factory.begin() as s:
        await s.execute(
            text(
                "INSERT INTO folders (id, user_id, name, created_at) VALUES"
                " ('fld_exp_p', :u, '상위', now());"
            ),
            {"u": _U},
        )
        await s.execute(
            text(
                "INSERT INTO folders (id, user_id, parent_folder_id, name, created_at) VALUES"
                " ('fld_exp_c', :u, 'fld_exp_p', '하위/폴더', now())"
            ),
            {"u": _U},
        )
        await s.execute(
            text(
                "INSERT INTO journal_entries (id, user_id, date_key, title, content, retro_type,"
                " folder_id, created_at, deleted_at) VALUES"
                " ('ent_exp_1', :u, '2026-11-16', '회고 하나', '본문1', 'daily', 'fld_exp_c',"
                "  now(), NULL),"
                " ('ent_exp_2', :u, '2026-11-15', '지운 회고', '본문2', 'daily', NULL,"
                "  now(), now()),"
                " ('ent_exp_3', :u, '2026-11-14', '미분류 회고', '본문3', 'daily', NULL,"
                "  now(), NULL)"
            ),
            {"u": _U},
        )
        await s.execute(
            text(
                "INSERT INTO todos (id, user_id, title, status, date_key, created_at, tags,"
                " recurrence_rule, deleted_at) VALUES"
                " ('todo_exp_1', :u, '끝낸 일', 'done', '2026-10-30', now(), '{일}', NULL, NULL),"
                " ('todo_exp_2', :u, '매일', 'not-start', '2026-11-01', now(), '{}',"
                '  \'{"unit": "day", "interval": 1}\', NULL),'
                " ('todo_exp_3', :u, '지운 일', 'not-start', '2026-11-02', now(), '{}',"
                "  NULL, now())"
            ),
            {"u": _U},
        )
        await s.execute(
            text(
                "INSERT INTO ai_conversations (id, user_id, title, created_at) VALUES"
                " ('conv_exp', :u, '계획', now())"
            ),
            {"u": _U},
        )
        await s.execute(
            text(
                "INSERT INTO ai_messages (id, conversation_id, role, content, created_at) VALUES"
                " ('msg_exp_1', 'conv_exp', 'user', '내일 정리해줘', now()),"
                " ('msg_exp_2', 'conv_exp', 'assistant', '정리했어요', now())"
            ),
        )

    md = ExportJob("exp_md", _U, ["retro", "todo", "ai"], "md", "pending", datetime.now(UTC))
    js = ExportJob("exp_js", _U, ["retro", "todo", "ai"], "json", "pending", datetime.now(UTC))
    async with factory.begin() as s:
        await build_export(s, md, tmp_path / "md.zip")
        await build_export(s, js, tmp_path / "js.zip")

    with zipfile.ZipFile(tmp_path / "md.zip") as zf:
        names = set(zf.namelist())
        assert "retro/상위/하위_폴더/2026-11-16-daily-회고 하나.md" in names
        assert "retro/미분류/2026-11-14-daily-미분류 회고.md" in names
        assert not any("지운" in n for n in names)
        assert {"todo/2026-10.md", "todo/2026-11.md"} <= names
        nov = zf.read("todo/2026-11.md").decode()
        assert "매일 (반복)" in nov and "지운 일" not in nov
        assert "- [x] 2026-10-30 끝낸 일 #일" in zf.read("todo/2026-10.md").decode()
        ai = [n for n in names if n.startswith("ai/")]
        assert len(ai) == 1 and "정리했어요" in zf.read(ai[0]).decode()

    with zipfile.ZipFile(tmp_path / "js.zip") as zf:
        retro = json.loads(zf.read("retro.json"))
        todos = json.loads(zf.read("todo.json"))
        convs = json.loads(zf.read("ai.json"))
        assert {r["id"] for r in retro} == {"ent_exp_1", "ent_exp_3"}
        assert {t["id"] for t in todos} == {"todo_exp_1", "todo_exp_2"}
        assert next(t for t in todos if t["id"] == "todo_exp_2")["recurrenceRule"]["unit"] == "day"
        assert [m["role"] for m in convs[0]["messages"]] == ["user", "assistant"]


async def test_empty_scopes_produce_valid_empty_json(factory, tmp_path):
    job = ExportJob(
        "exp_empty", _OTHER, ["retro", "todo", "ai"], "json", "pending", datetime.now(UTC)
    )
    async with factory.begin() as s:
        await build_export(s, job, tmp_path / "e.zip")
    with zipfile.ZipFile(tmp_path / "e.zip") as zf:
        assert json.loads(zf.read("retro.json")) == [] and json.loads(zf.read("ai.json")) == []
