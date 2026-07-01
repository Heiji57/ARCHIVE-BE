"""summary content JSONB → TEXT (마크다운 직접 저장)

Revision ID: 023
Revises: 022
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def _jsonb_to_markdown(content: dict) -> str:
    """기존 JSONB sections 구조를 마크다운으로 변환."""
    if not content:
        return ""

    sections = content.get("sections")

    # 신규 배열 형식: {"sections": [{"key": k, "items": [...]}]}
    if isinstance(sections, list):
        parts: list[str] = []
        for section in sections:
            if not isinstance(section, dict) or "key" not in section:
                continue
            parts.append(f"## {section['key']}")
            for item in section.get("items", []):
                if item:
                    parts.append(f"- {item}")
        return "\n".join(parts)

    # 레거시 flat dict 형식: {"achievements": [...], ...}
    parts = []
    for key, items in content.items():
        if isinstance(items, list):
            parts.append(f"## {key}")
            for item in items:
                if item:
                    parts.append(f"- {item}")
    return "\n".join(parts)


def _markdown_to_jsonb(text: str) -> dict:
    """마크다운을 JSONB sections 배열 형식으로 역변환 (downgrade 용)."""
    if not text:
        return {"sections": []}

    sections: list[dict] = []
    current_key: str | None = None
    current_items: list[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            if current_key is not None:
                sections.append({"key": current_key, "items": current_items})
            current_key = stripped.lstrip("#").strip()
            current_items = []
        elif stripped.startswith("- ") and current_key is not None:
            current_items.append(stripped[2:].strip())

    if current_key is not None:
        sections.append({"key": current_key, "items": current_items})

    return {"sections": sections}


def upgrade() -> None:
    conn = op.get_bind()

    # 1. 임시 TEXT 컬럼 추가
    op.add_column(
        "retro_summaries",
        sa.Column("content_text", sa.Text, nullable=True),
    )

    # 2. 기존 JSONB → 마크다운 변환
    rows = conn.execute(
        sa.text("SELECT id, content FROM retro_summaries WHERE content IS NOT NULL")
    ).fetchall()

    for row_id, content in rows:
        md = _jsonb_to_markdown(content)
        conn.execute(
            sa.text("UPDATE retro_summaries SET content_text = :md WHERE id = :id"),
            {"md": md, "id": row_id},
        )

    # 3. 기존 JSONB 컬럼 제거
    op.drop_column("retro_summaries", "content")

    # 4. 임시 컬럼을 content 로 이름 변경
    op.alter_column("retro_summaries", "content_text", new_column_name="content")


def downgrade() -> None:
    conn = op.get_bind()

    # 1. 임시 JSONB 컬럼 추가
    op.add_column(
        "retro_summaries",
        sa.Column("content_jsonb", postgresql.JSONB, nullable=True),
    )

    # 2. 마크다운 → JSONB 역변환
    rows = conn.execute(
        sa.text("SELECT id, content FROM retro_summaries WHERE content IS NOT NULL")
    ).fetchall()

    for row_id, text in rows:
        data = _markdown_to_jsonb(text or "")
        conn.execute(
            sa.text(
                "UPDATE retro_summaries SET content_jsonb = :data::jsonb WHERE id = :id"
            ),
            {"data": sa.func.cast(str(data), postgresql.JSONB), "id": row_id},
        )

    # 3. TEXT 컬럼 제거
    op.drop_column("retro_summaries", "content")

    # 4. 임시 컬럼을 content 로 이름 변경
    op.alter_column("retro_summaries", "content_jsonb", new_column_name="content")
