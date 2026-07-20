"""add commit_read_enabled to github_repositories + github_push_target_repository_id to user_settings

Revision ID: 010
Revises: 009
Create Date: 2026-06-04

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "github_repositories",
        sa.Column(
            "commit_read_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
    )
    op.add_column(
        "user_settings",
        sa.Column("github_push_target_repository_id", sa.String(), nullable=True),
    )
    op.create_foreign_key(
        "fk_user_settings_push_target",
        "user_settings",
        "github_repositories",
        ["github_push_target_repository_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_user_settings_push_target", "user_settings", type_="foreignkey")
    op.drop_column("user_settings", "github_push_target_repository_id")
    op.drop_column("github_repositories", "commit_read_enabled")
