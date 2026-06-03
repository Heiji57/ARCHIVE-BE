"""add github_repositories table

Revision ID: 008
Revises: 007
Create Date: 2026-06-03

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "github_repositories",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("github_repo_id", sa.BigInteger(), nullable=False),
        sa.Column("owner", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(512), nullable=False),
        sa.Column("is_private", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("default_branch", sa.String(255), nullable=False),
        sa.Column("html_url", sa.String(1024), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "github_repo_id", name="uq_github_repositories_user_repo"
        ),
    )
    op.create_index(
        "ix_github_repositories_user_id", "github_repositories", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_github_repositories_user_id", table_name="github_repositories")
    op.drop_table("github_repositories")
