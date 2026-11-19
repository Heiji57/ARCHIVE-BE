"""내보내기 zip 만들기 — 회고·할 일·AI 대화를 Markdown 또는 JSON 으로.

- 휴지통의 할 일·회고는 soft delete 리스너로 자동으로 빠진다.
- 큰 데이터(회고 1,000편)에서도 메모리에 다 올리지 않게 행을 나눠 읽고(yield_per) zip 에 바로 쓴다.
  JSON 은 배열을 항목 단위로 이어 쓴다.

| 범위 | Markdown | JSON |
|---|---|---|
| retro | 폴더 구조대로 회고 한 편당 파일 하나(머리에 날짜·종류) | retro.json |
| todo | 월별 파일 하나(날짜·상태 목록) | todo.json(반복 규칙 포함) |
| ai | 대화별 파일 | ai.json(대화와 메시지) |
"""

import json
import re
import zipfile
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.infrastructure.persistence.models.conversation_model import (
    AiConversationModel,
    AiMessageModel,
)
from app.data.domain.models.export import ExportJob
from app.retrospective.infrastructure.persistence.models.folder_model import FolderModel
from app.retrospective.infrastructure.persistence.models.journal_entry_model import (
    JournalEntryModel,
)
from app.todo.infrastructure.persistence.models.todo_model import TodoModel

_BATCH = 200
_UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')
_STATUS_MARK = {"done": "x", "in-progress": "~", "cancelled": "-"}


def _safe(name: str, fallback: str) -> str:
    cleaned = _UNSAFE.sub("_", name).strip(" .")[:60]
    return cleaned or fallback


async def _rows(session: AsyncSession, stmt: Any) -> AsyncIterator[Any]:
    result = await session.stream_scalars(stmt.execution_options(yield_per=_BATCH))
    async for row in result:
        yield row


@contextmanager
def _json_array(zf: zipfile.ZipFile, name: str) -> Iterator[Any]:
    with zf.open(name, "w") as raw:
        first = [True]

        def write(item: dict[str, Any]) -> None:
            raw.write(b"[\n" if first[0] else b",\n")
            first[0] = False
            raw.write(json.dumps(item, ensure_ascii=False, default=str).encode())

        yield write
        raw.write(b"[]" if first[0] else b"\n]\n")


def _text(handle: IO[bytes], text: str) -> None:
    handle.write(text.encode())


async def build_export(session: AsyncSession, job: ExportJob, target: Path) -> None:
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if "retro" in job.scopes:
            await _retros(session, job, zf)
        if "todo" in job.scopes:
            await _todos(session, job, zf)
        if "ai" in job.scopes:
            await _ai(session, job, zf)


# ── 회고 ──────────────────────────────────────────────────────────────────


async def _folder_paths(session: AsyncSession, user_id: str) -> dict[str, str]:
    rows = (
        await session.execute(
            select(FolderModel.id, FolderModel.parent_folder_id, FolderModel.name).where(
                FolderModel.user_id == user_id
            )
        )
    ).all()
    by_id = {r.id: r for r in rows}
    paths: dict[str, str] = {}

    def path(fid: str, depth: int = 0) -> str:
        if fid in paths:
            return paths[fid]
        row = by_id[fid]
        name = _safe(row.name, fid)
        parent = row.parent_folder_id
        # 순환 데이터가 있어도 끝나게 깊이를 막는다.
        full = f"{path(parent, depth + 1)}/{name}" if parent in by_id and depth < 32 else name
        paths[fid] = full
        return full

    for fid in by_id:
        path(fid)
    return paths


async def _retros(session: AsyncSession, job: ExportJob, zf: zipfile.ZipFile) -> None:
    stmt = (
        select(JournalEntryModel)
        .where(JournalEntryModel.user_id == job.user_id)
        .order_by(JournalEntryModel.date_key, JournalEntryModel.id)
    )
    if job.format == "json":
        with _json_array(zf, "retro.json") as write:
            async for e in _rows(session, stmt):
                write(
                    {
                        "id": e.id,
                        "dateKey": e.date_key,
                        "retroType": e.retro_type,
                        "title": e.title,
                        "content": e.content,
                        "folderId": e.folder_id,
                        "createdAt": e.created_at,
                        "updatedAt": e.updated_at,
                    }
                )
        return
    folders = await _folder_paths(session, job.user_id)
    used: set[str] = set()
    async for e in _rows(session, stmt):
        base = folders.get(e.folder_id or "", "미분류")
        name = f"retro/{base}/{e.date_key}-{e.retro_type}-{_safe(e.title, 'untitled')}"
        if name in used:
            name = f"{name}-{e.id[-6:]}"
        used.add(name)
        with zf.open(f"{name}.md", "w") as f:
            _text(f, f"# {e.title}\n\n- 날짜: {e.date_key}\n- 종류: {e.retro_type}\n\n")
            _text(f, e.content or "")
            _text(f, "\n")


# ── 할 일 ─────────────────────────────────────────────────────────────────


async def _todos(session: AsyncSession, job: ExportJob, zf: zipfile.ZipFile) -> None:
    stmt = (
        select(TodoModel)
        .where(TodoModel.user_id == job.user_id)
        .order_by(TodoModel.date_key, TodoModel.created_at, TodoModel.id)
    )
    if job.format == "json":
        with _json_array(zf, "todo.json") as write:
            async for t in _rows(session, stmt):
                write(
                    {
                        "id": t.id,
                        "title": t.title,
                        "status": t.status,
                        "dateKey": t.date_key,
                        "dueDateKey": t.due_date_key,
                        "description": t.description,
                        "startTime": t.start_time,
                        "endTime": t.end_time,
                        "timezone": t.timezone,
                        "tags": list(t.tags or []),
                        "recurrenceRule": t.recurrence_rule,
                        "seriesId": t.series_id,
                        "originalDateKey": t.original_date_key,
                        "calendarId": t.calendar_id,
                        "completedAt": t.completed_at,
                        "createdAt": t.created_at,
                    }
                )
        return
    month: str | None = None
    handle: IO[bytes] | None = None
    try:
        async for t in _rows(session, stmt):
            if t.date_key[:7] != month:
                if handle is not None:
                    handle.close()
                month = t.date_key[:7]
                handle = zf.open(f"todo/{month}.md", "w")
                _text(handle, f"# {month}\n\n")
            assert handle is not None
            mark = _STATUS_MARK.get(t.status, " ")
            repeat = " (반복)" if t.recurrence_rule and not t.series_id else ""
            tags = " " + " ".join(f"#{x}" for x in t.tags) if t.tags else ""
            _text(handle, f"- [{mark}] {t.date_key} {t.title}{repeat}{tags}\n")
    finally:
        if handle is not None:
            handle.close()


# ── AI 대화 ───────────────────────────────────────────────────────────────


async def _ai(session: AsyncSession, job: ExportJob, zf: zipfile.ZipFile) -> None:
    conversations = (
        (
            await session.execute(
                select(AiConversationModel)
                .where(AiConversationModel.user_id == job.user_id)
                .order_by(AiConversationModel.created_at)
            )
        )
        .scalars()
        .all()
    )
    writer = _json_array(zf, "ai.json") if job.format == "json" else None
    write = writer.__enter__() if writer else None
    try:
        for c in conversations:
            messages = (
                select(AiMessageModel)
                .where(AiMessageModel.conversation_id == c.id, AiMessageModel.content != "")
                .order_by(AiMessageModel.created_at)
            )
            if write is not None:
                write(
                    {
                        "id": c.id,
                        "title": c.title,
                        "createdAt": c.created_at,
                        "messages": [
                            {"role": m.role, "content": m.content, "createdAt": m.created_at}
                            async for m in _rows(session, messages)
                        ],
                    }
                )
                continue
            day = c.created_at.date().isoformat()
            with zf.open(f"ai/{day}-{_safe(c.title, c.id)}-{c.id[-6:]}.md", "w") as f:
                _text(f, f"# {c.title or 'AI'}\n\n")
                async for m in _rows(session, messages):
                    who = "나" if m.role == "user" else "AI"
                    _text(f, f"**{who}** ({m.created_at.isoformat()})\n\n{m.content}\n\n")
    finally:
        if writer is not None:
            writer.__exit__(None, None, None)
