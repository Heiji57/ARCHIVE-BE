"""통합검색 범위(`GET /search?scope=`) — 범위 밖 종류는 조회하지 않고 빈 목록."""
from datetime import UTC, datetime

import pytest

from app.search.application.use_cases.global_search import GlobalSearchUseCase
from app.search.presentation.responses.responses import GlobalSearchResponse
from app.topic.domain.models.topic import Topic


class _Recorder:
    def __init__(self, name: str, calls: list[str], result=None) -> None:
        self._name = name
        self._calls = calls
        self._result = result

    async def find_by_full_text(self, user_id, q, page, size):
        self._calls.append(self._name)
        return [], 0

    async def search(self, user_id, q, limit):
        self._calls.append(self._name)
        return self._result or []


def _uc(calls: list[str], topics=None) -> GlobalSearchUseCase:
    return GlobalSearchUseCase(
        _Recorder("todo", calls),  # type: ignore[arg-type]
        _Recorder("retro", calls),  # type: ignore[arg-type]
        _Recorder("topic", calls, topics),  # type: ignore[arg-type]
    )


@pytest.mark.parametrize(
    ("scope", "expected"),
    [
        ("all", {"todo", "retro", "topic"}),
        ("todo", {"todo"}),
        ("retro", {"retro"}),
        ("topic", {"topic"}),
    ],
)
async def test_scope_selects_sources(scope, expected):
    calls: list[str] = []
    await _uc(calls).execute("usr_1", "q", 5, scope)
    assert set(calls) == expected


async def test_topics_are_returned_in_response():
    topic = Topic(
        id="topic_1",
        user_id="usr_1",
        name="무한 스크롤",
        description="월간 뷰",
        created_at=datetime(2026, 11, 1, tzinfo=UTC),
    )
    result = await _uc([], [topic]).execute("usr_1", "스크롤", 5, "topic")
    body = GlobalSearchResponse.from_result(result).model_dump()
    assert body["topics"] == [{"id": "topic_1", "name": "무한 스크롤", "description": "월간 뷰"}]
    assert body["todos"] == [] and body["entries"] == []
