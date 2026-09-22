"""check-then-insert 경쟁에서 진 요청이 IntegrityError(500) 대신 사전 체크와 같은 409 를 받는지.

유스케이스는 저장 전에 중복을 조회하지만, 동시 요청 둘이 모두 조회를 통과하면 늦은 쪽의
flush 가 unique 제약에 걸린다. 각 repository 가 "제약 이름 → 도메인 예외" 를 선언하고
flush 를 감싼다. 매핑에 없는 제약(FK 등)은 코드/데이터 문제라 그대로 전파해야 한다.
"""
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.shared.infrastructure.database.errors import (
    constraint_name,
    translate_unique_violations,
)
from app.topic.domain.exceptions.exceptions import (
    DigestAlreadyInProgressException,
    TopicNameDuplicatedException,
)
from app.user.domain.exceptions.exceptions import UserEmailDuplicatedException


class _AsyncpgUniqueViolationError(Exception):
    def __init__(self, constraint: str) -> None:
        super().__init__(f'duplicate key value violates unique constraint "{constraint}"')
        self.constraint_name = constraint


class _DbapiWrapperError(Exception):
    """SQLAlchemy asyncpg 어댑터: orig 는 래퍼, 실제 asyncpg 예외는 __cause__."""


def _integrity_error(constraint: str, *, wrapped: bool = False) -> IntegrityError:
    orig: Exception = _AsyncpgUniqueViolationError(constraint)
    if wrapped:
        wrapper = _DbapiWrapperError(str(orig))
        wrapper.__cause__ = orig
        orig = wrapper
    return IntegrityError("INSERT ...", {}, orig)


def test_constraint_name_from_orig_cause_or_message():
    assert constraint_name(_integrity_error("uq_a")) == "uq_a"
    assert constraint_name(_integrity_error("uq_b", wrapped=True)) == "uq_b"
    message_only = IntegrityError(
        "INSERT", {}, Exception('violates unique constraint "uq_c"')
    )
    assert constraint_name(message_only) == "uq_c"


async def test_mapped_constraint_becomes_domain_exception():
    with pytest.raises(UserEmailDuplicatedException) as ei:
        async with translate_unique_violations({"users_email_key": UserEmailDuplicatedException}):
            raise _integrity_error("users_email_key", wrapped=True)
    assert isinstance(ei.value.__cause__, IntegrityError)


async def test_unmapped_constraint_propagates():
    with pytest.raises(IntegrityError):
        async with translate_unique_violations({"users_email_key": UserEmailDuplicatedException}):
            raise _integrity_error("fk_something")


class _Session:
    def __init__(self, constraint: str) -> None:
        self._constraint = constraint

    async def merge(self, model):
        return model

    async def flush(self):
        raise _integrity_error(self._constraint, wrapped=True)


async def test_user_repo_save_race_on_email_is_409_exception():
    from app.user.domain.models.user import User
    from app.user.domain.models.value_objects import Email
    from app.user.infrastructure.persistence.repositories.user_repo import UserRepository

    user = User(
        id="usr_1",
        created_at=datetime.now(UTC),
        email=Email("a@b.com"),
        password_hash=None,
        country="KR",
        region=None,
        timezone="Asia/Seoul",
    )
    with pytest.raises(UserEmailDuplicatedException):
        await UserRepository(_Session("users_email_key")).save(user)


async def test_topic_and_digest_repos_use_their_own_mappings():
    from app.topic.domain.models.topic import Topic, TopicDigest
    from app.topic.domain.models.value_objects import DigestStatus
    from app.topic.infrastructure.persistence.repositories.topic_repo import (
        TopicDigestRepository,
        TopicRepository,
    )

    now = datetime.now(UTC)
    topic = Topic(id="tpc_1", user_id="u1", name="n", description=None, created_at=now)
    with pytest.raises(TopicNameDuplicatedException):
        await TopicRepository(_Session("uq_topics_user_name")).save(topic)

    digest = TopicDigest(
        id="dig_1", topic_id="tpc_1", user_id="u1", status=DigestStatus.PENDING, created_at=now
    )
    with pytest.raises(DigestAlreadyInProgressException):
        await TopicDigestRepository(_Session("uq_topic_digests_topic_user")).save(digest)
    # 다른 테이블의 제약 이름은 매핑하지 않는다 — digest repo 에서 topic 제약이 나오면 버그다.
    with pytest.raises(IntegrityError):
        await TopicDigestRepository(_Session("uq_topics_user_name")).save(digest)


async def test_folder_and_retro_template_repos_translate_name_races():
    """folders 는 028 의 COALESCE 표현식 인덱스, retro_templates 는 036 의 인덱스 —
    둘 다 인덱스 이름이 constraint_name 으로 온다 (일회용 Postgres 에서 실측 확인)."""
    from app.retrospective.domain.exceptions.exceptions import (
        FolderNameDuplicatedException,
        RetroTemplateNameDuplicatedException,
    )
    from app.retrospective.domain.models.folder import Folder
    from app.retrospective.domain.models.retro_template import RetroTemplate
    from app.retrospective.domain.models.value_objects import RetroType
    from app.retrospective.infrastructure.persistence.repositories.folder_repo import (
        FolderRepository,
    )
    from app.retrospective.infrastructure.persistence.repositories.retro_template_repo import (
        RetroTemplateRepository,
    )

    now = datetime.now(UTC)
    folder = Folder(id="f1", user_id="u1", parent_folder_id=None, name="A", created_at=now)
    with pytest.raises(FolderNameDuplicatedException):
        await FolderRepository(_Session("uq_folders_user_parent_name")).save(folder)

    template = RetroTemplate(
        id="tmpl_1", user_id="u1", retro_type=RetroType("daily"), name="n", content="c",
        is_default=False, created_at=now,
    )
    with pytest.raises(RetroTemplateNameDuplicatedException):
        await RetroTemplateRepository(_Session("uq_retro_templates_user_type_name")).save(template)
