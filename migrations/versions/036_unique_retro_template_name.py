"""retro_templates (user_id, retro_type, name) 유니크 인덱스

유스케이스의 이름 중복 사전 체크는 동시 요청 경쟁을 막지 못해 같은 이름이 두 번 저장될 수
있었다(folders 는 028 에서 이미 DB 유니크 인덱스를 둠). DB 제약을 추가하고, repository 가
제약 위반을 RetroTemplateNameDuplicatedException(409)로 번역한다.

기존 데이터에 이미 중복이 있으면 인덱스 생성이 실패하므로, 먼저 가장 오래된 행만 원래
이름으로 두고 나머지는 이름 뒤에 id 꼬리를 붙여 유일하게 만든다(데이터 삭제 없음).

리비전 체인: 병렬 브랜치(035, todo 시간 보정)와 동시에 개발돼 둘 다 down=034 로 머지됐고
그 결과 head 가 둘로 갈려 `alembic upgrade head` 가 "Multiple head revisions" 로 실패했다.
두 마이그레이션은 서로 독립적이므로 이 쪽을 035 뒤로 이어 단일 head 로 되돌린다.

Revision ID: 036
Revises: 035
Create Date: 2026-09-22
"""
from typing import Sequence, Union

from alembic import op

revision: str = "036"
down_revision: Union[str, None] = "035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # name 은 VARCHAR(120) — 꼬리(" (xxxxxxxx)", 11자)를 붙일 자리를 남기고 자른다.
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY user_id, retro_type, name
                       ORDER BY created_at, id
                   ) AS rn
            FROM retro_templates
        )
        UPDATE retro_templates AS t
        SET name = LEFT(t.name, 109) || ' (' || RIGHT(t.id, 8) || ')'
        FROM ranked
        WHERE t.id = ranked.id AND ranked.rn > 1
        """
    )
    op.create_index(
        "uq_retro_templates_user_type_name",
        "retro_templates",
        ["user_id", "retro_type", "name"],
        unique=True,
    )


def downgrade() -> None:
    # 이름 변경은 되돌리지 않는다 — 원래 중복 상태로 되돌릴 이유가 없다.
    op.drop_index("uq_retro_templates_user_type_name", table_name="retro_templates")
