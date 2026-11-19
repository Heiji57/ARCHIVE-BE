"""구조화 주제 정리 — 모델 출력 검증·정리(`normalize`)와 재요청.

모델은 근거를 표식(E1, T1)으로만 가리키고, 서버가 실제 id·날짜로 바꾼다.
모르는 표식·빈 큰 주제는 버리고, 큰 주제 순서(=FE 색)는 날짜로 안정적으로 정한다.
"""
import pytest

from app.topic.domain.models.structured_digest import (
    MAX_ITEM_TEXT,
    MAX_ITEMS_PER_THEME,
    MAX_THEMES,
    SourceRef,
    StructuredDigest,
    normalize,
)
from app.worker.tasks.generate_digest import (
    DigestInvalidOutputError,
    SourceLabels,
    _generate_structured,
    _label_sources,
)

_SOURCES = {
    "E1": SourceRef("entry", "ent_a", "2026-10-21"),
    "E2": SourceRef("entry", "ent_b", "2026-10-29"),
    "T1": SourceRef("todo", "todo_x", "2026-10-25"),
}


def _theme(name: str, *items: tuple[str, str]) -> dict:
    return {
        "name": name,
        "summary": f"{name} 요약",
        "items": [{"source": s, "text": t} for s, t in items],
    }


def test_labels_become_ids_and_dates_come_from_sources():
    raw = {
        "summary": "끝냈다",
        "themes": [_theme("스크롤", ("E1", "위치 보정"), ("T1", "공용 로직"))],
        "dateKey": "1999-01-01",
    }
    d = normalize(raw, _SOURCES)
    items = d.themes[0].items
    assert [(i.source_kind, i.source_id, i.date_key) for i in items] == [
        ("entry", "ent_a", "2026-10-21"),
        ("todo", "todo_x", "2026-10-25"),
    ]


def test_unknown_labels_and_empty_themes_are_dropped():
    raw = {
        "summary": "s",
        "themes": [
            _theme("유령", ("E9", "지어낸 근거")),
            _theme("진짜", ("E2", "있는 근거"), ("T7", "없는 할 일")),
        ],
    }
    d = normalize(raw, _SOURCES)
    assert [t.name for t in d.themes] == ["진짜"]
    assert [i.source_id for i in d.themes[0].items] == ["ent_b"]


def test_themes_sorted_by_earliest_item_and_rekeyed():
    raw = {
        "summary": "s",
        "themes": [
            _theme("나중", ("E2", "b")),
            _theme("먼저", ("E1", "a")),
        ],
    }
    d = normalize(raw, _SOURCES)
    assert [(t.key, t.name) for t in d.themes] == [("t1", "먼저"), ("t2", "나중")]


def test_limits_are_enforced():
    sources = {f"E{i}": SourceRef("entry", f"e{i}", f"2026-10-{i:02d}") for i in range(1, 21)}
    raw = {
        "summary": "x" * 300,
        "themes": [
            _theme(f"주제 이름이 아주 아주 길다 {n}", *[(f"E{i}", "t" * 300) for i in range(1, 21)])
            for n in range(MAX_THEMES + 3)
        ],
    }
    d = normalize(raw, sources)
    assert len(d.themes) == MAX_THEMES
    assert all(len(t.items) == MAX_ITEMS_PER_THEME for t in d.themes)
    assert all(len(t.name) <= 20 for t in d.themes)
    assert len(d.summary) <= 100
    assert all(len(i.text) <= MAX_ITEM_TEXT for t in d.themes for i in t.items)


def test_same_source_may_appear_in_several_themes():
    raw = {"summary": "s", "themes": [_theme("가", ("E1", "x")), _theme("나", ("E1", "y"))]}
    d = normalize(raw, _SOURCES)
    assert [t.items[0].source_id for t in d.themes] == ["ent_a", "ent_a"]


def test_round_trip_and_markdown():
    d = normalize(
        {"summary": "요약", "themes": [_theme("스크롤", ("E1", "위치 보정"))]}, _SOURCES
    )
    assert StructuredDigest.from_dict(d.to_dict()) == d
    assert d.to_dict()["themes"][0]["items"][0] == {
        "dateKey": "2026-10-21",
        "text": "위치 보정",
        "source": {"kind": "entry", "id": "ent_a"},
    }
    assert d.to_markdown() == "요약\n\n## 스크롤\n스크롤 요약\n- 10/21 위치 보정"
    assert d.period() == ("2026-10-21", "2026-10-21")


def test_recent_items_excludes_future_and_sorts_desc():
    d = normalize(
        {"summary": "s", "themes": [_theme("가", ("E1", "a"), ("E2", "b"), ("T1", "c"))]},
        _SOURCES,
    )
    recent = d.recent_items("2026-10-26", limit=5)
    assert [(i.text, key) for i, key in recent] == [("c", "t1"), ("a", "t1")]


# ── 재요청 ───────────────────────────────────────────────────────────────


class _Gemini:
    def __init__(self, outputs: list) -> None:
        self._outputs = outputs
        self.calls = 0

    async def generate_json(self, prompt, schema):
        out = self._outputs[self.calls]
        self.calls += 1
        if isinstance(out, Exception):
            raise out
        return out


_LABELS = SourceLabels(by_label=_SOURCES, entry_label={}, todo_label={})
_GOOD = {"summary": "s", "themes": [_theme("가", ("E1", "a"))]}


async def test_retries_once_on_invalid_json_then_succeeds():
    gemini = _Gemini([ValueError("bad json"), _GOOD])
    d = await _generate_structured(gemini, "p", _LABELS, "dig_1")
    assert gemini.calls == 2 and d.themes[0].name == "가"


async def test_retries_when_no_item_survives_then_fails():
    bad = {"summary": "s", "themes": [_theme("가", ("E99", "없는 근거"))]}
    gemini = _Gemini([bad, bad])
    with pytest.raises(DigestInvalidOutputError):
        await _generate_structured(gemini, "p", _LABELS, "dig_1")
    assert gemini.calls == 2


async def test_empty_result_is_fine_without_sources():
    gemini = _Gemini([{"summary": "", "themes": []}])
    empty = SourceLabels(by_label={}, entry_label={}, todo_label={})
    d = await _generate_structured(gemini, "p", empty, "dig_1")
    assert d.themes == [] and gemini.calls == 1


def test_label_sources_orders_entries_then_previous_only_sources():
    from types import SimpleNamespace

    chunks = [
        SimpleNamespace(entry_id="b", chunk_index=0, date_key="2026-10-02"),
        SimpleNamespace(entry_id="a", chunk_index=0, date_key="2026-10-01"),
        SimpleNamespace(entry_id="b", chunk_index=1, date_key="2026-10-02"),
    ]
    todos = [SimpleNamespace(todo_id="t", date_key="2026-10-03")]
    previous = normalize(
        {"summary": "s", "themes": [_theme("가", ("E1", "옛"))]},
        {"E1": SourceRef("entry", "old", "2026-09-01")},
    )
    labels = _label_sources(chunks, todos, previous)
    assert labels.entry_label == {"b": "E1", "a": "E2", "old": "E3"}
    assert labels.todo_label == {"t": "T1"}
    assert labels.by_label["E3"] == SourceRef("entry", "old", "2026-09-01")


def test_over_limit_keeps_newest_items_and_recent_themes():
    sources = {f"E{i}": SourceRef("entry", f"e{i}", f"2026-10-{i:02d}") for i in range(1, 21)}
    raw = {"summary": "s", "themes": [_theme("가", *[(f"E{i}", f"t{i}") for i in range(1, 21)])]}
    items = normalize(raw, sources).themes[0].items
    assert items[0].source_id == "e9" and items[-1].source_id == "e20"

    themes = [_theme(f"주제{i}", (f"E{i}", "x")) for i in range(1, MAX_THEMES + 3)]
    kept = normalize({"summary": "s", "themes": themes}, sources).themes
    # 가장 오래된 두 주제(E1, E2)가 밀려나고 나머지는 날짜 순 + t1.. 재매김
    assert [t.items[0].source_id for t in kept] == [f"e{i}" for i in range(3, MAX_THEMES + 3)]
    assert kept[0].key == "t1"
