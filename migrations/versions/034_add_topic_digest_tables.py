"""add topic digest tables (pgvector embeddings)

Revision ID: 034
Revises: 033
Create Date: 2026-08-31
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "034"
down_revision: Union[str, None] = "033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # pgvector extension (이미 존재하면 무시)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "topics",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "name", name="uq_topics_user_name"),
    )
    op.create_index("ix_topics_user_id", "topics", ["user_id"])

    op.create_table(
        "topic_digests",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("topic_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("watermark_date_key", sa.String(10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("topic_id", "user_id", name="uq_topic_digests_topic_user"),
    )
    op.create_index("ix_topic_digests_user_id", "topic_digests", ["user_id"])

    op.create_table(
        "topic_entry_chunks",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("entry_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("date_key", sa.String(10), nullable=False),
        sa.Column("embedding", sa.Text(), nullable=True),  # overridden by vector type below
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("entry_id", "chunk_index", name="uq_entry_chunks_entry_idx"),
    )
    # Replace TEXT column with proper vector type
    op.execute("ALTER TABLE topic_entry_chunks ALTER COLUMN embedding TYPE vector(768) USING embedding::vector(768)")
    op.create_index("ix_entry_chunks_user_id", "topic_entry_chunks", ["user_id"])
    op.create_index("ix_entry_chunks_user_date", "topic_entry_chunks", ["user_id", "date_key"])
    op.execute(
        "CREATE INDEX ix_entry_chunks_embedding_hnsw ON topic_entry_chunks "
        "USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64)"
    )

    op.create_table(
        "topic_todo_embeddings",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("todo_id", sa.String(), nullable=False, unique=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("date_key", sa.String(10), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("embedding", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.execute("ALTER TABLE topic_todo_embeddings ALTER COLUMN embedding TYPE vector(768) USING embedding::vector(768)")
    op.create_index("ix_todo_embeddings_user_id", "topic_todo_embeddings", ["user_id"])
    op.create_index("ix_todo_embeddings_user_date", "topic_todo_embeddings", ["user_id", "date_key"])
    op.execute(
        "CREATE INDEX ix_todo_embeddings_embedding_hnsw ON topic_todo_embeddings "
        "USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64)"
    )

    op.create_table(
        "topic_embedding_queue",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("entity_type", sa.String(10), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("entity_type", "entity_id", name="uq_embedding_queue_entity"),
    )
    op.create_index("ix_embedding_queue_user_id", "topic_embedding_queue", ["user_id"])


def downgrade() -> None:
    op.drop_table("topic_embedding_queue")
    op.drop_table("topic_todo_embeddings")
    op.drop_table("topic_entry_chunks")
    op.drop_table("topic_digests")
    op.drop_table("topics")
