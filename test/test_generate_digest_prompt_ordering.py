"""digest 프롬프트 조립 — 청크가 유사도 순으로 뒤섞여 와도 entry 별로 안 갈라지는지.

GitHub #1: `_build_prompt` 가 entry_id 를 처음 볼 때만 날짜 헤딩을 찍고 이후 청크를
그대로 이어붙였다. `search_similar` 결과는 entry_id 로 묶여 오지 않고 코사인 거리
순이라, 한 entry 의 두 번째 청크가 다른 entry 의 헤딩 밑에 잘못 실렸다.
`topic_search_limit` 을 50→200 으로 올리면서(2026-09-09) 한 주제에 여러 청크를 가진
entry 가 늘어 상시 발생 조건이 됐다.
"""
from dataclasses import dataclass

from app.worker.tasks.generate_digest import _build_prompt


@dataclass(frozen=True)
class _Chunk:
    entry_id: str
    chunk_index: int
    text: str
    date_key: str


async def test_interleaved_chunks_group_under_correct_entry_heading() -> None:
    """entry A 의 두 청크 사이에 entry B 의 청크가 유사도 순으로 끼어드는 시나리오."""
    chunks = [
        _Chunk(entry_id="e_a", chunk_index=0, text="A 첫 문단", date_key="2026-09-01"),
        _Chunk(entry_id="e_b", chunk_index=0, text="B 문단", date_key="2026-09-05"),
        _Chunk(entry_id="e_a", chunk_index=1, text="A 둘째 문단", date_key="2026-09-01"),
    ]

    prompt = await _build_prompt("배포", "배포 자동화", chunks, [])

    # A 의 두 문단이 모두 "2026-09-01" 헤딩 아래 있어야 한다 — B 의 날짜 밑으로
    # 새지 않아야 한다.
    a_heading_pos = prompt.index("**2026-09-01**")
    b_heading_pos = prompt.index("**2026-09-05**")
    a_second_pos = prompt.index("A 둘째 문단")

    assert a_heading_pos < a_second_pos, "A 둘째 문단이 A 헤딩보다 앞에 있다"
    # A 둘째 문단이 B 헤딩보다 뒤에 나타나면(B 섹션 안에 있으면) 오귀속이다.
    assert not (b_heading_pos < a_second_pos), (
        "A 의 둘째 청크가 B 의 날짜 헤딩 아래로 잘못 붙었다"
    )

    # 헤딩은 entry 당 정확히 한 번만 찍혀야 한다 (중복 헤딩 방지 회귀도 겸한다).
    assert prompt.count("**2026-09-01**") == 1
    assert prompt.count("**2026-09-05**") == 1


async def test_entry_order_preserved_by_first_occurrence() -> None:
    """entry 등장 순서(= 가장 유사한 청크 기준)는 정렬 후에도 보존돼야 한다."""
    chunks = [
        _Chunk(entry_id="e_first", chunk_index=0, text="가장 유사", date_key="2026-01-01"),
        _Chunk(entry_id="e_second", chunk_index=0, text="그다음", date_key="2026-01-02"),
    ]
    prompt = await _build_prompt("배포", "", chunks, [])
    assert prompt.index("**2026-01-01**") < prompt.index("**2026-01-02**")


async def test_chunks_within_entry_ordered_by_chunk_index() -> None:
    """같은 entry 안에서는 chunk_index 오름차순으로 재배치돼야 한다."""
    chunks = [
        _Chunk(entry_id="e_a", chunk_index=2, text="세 번째", date_key="2026-09-01"),
        _Chunk(entry_id="e_a", chunk_index=0, text="첫 번째", date_key="2026-09-01"),
        _Chunk(entry_id="e_a", chunk_index=1, text="두 번째", date_key="2026-09-01"),
    ]
    prompt = await _build_prompt("배포", "", chunks, [])
    assert (
        prompt.index("첫 번째") < prompt.index("두 번째") < prompt.index("세 번째")
    )
