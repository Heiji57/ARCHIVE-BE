"""구조화된 주제 정리 — 한 줄 요약 + 큰 주제(theme) + 날짜별 한 일(item) + 근거(source).

모델(LLM)은 근거를 UUID 가 아니라 짧은 표식(`E3`, `T5`)으로 가리킨다. 서버가 표식을
실제 id 로 바꾸고 검증·정리한다(`normalize`) — 모델이 id·날짜를 지어내는 일을 막는다.
markdown `content` 는 이 구조에서 만든다(`to_markdown`, 옛 클라이언트·내보내기용).
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

SourceKind = Literal["entry", "todo"]

STRUCTURE_VERSION = 1
MAX_THEMES = 6
MAX_ITEMS_PER_THEME = 12
MAX_THEME_NAME = 20
MAX_SUMMARY = 100
MAX_ITEM_TEXT = 120


@dataclass(frozen=True)
class SourceRef:
    """프롬프트에 실은 근거 하나 — 표식이 가리키는 실제 대상."""

    kind: SourceKind
    id: str
    date_key: str  # YYYY-MM-DD — 항목 날짜는 모델이 아니라 이 값으로 채운다


@dataclass(frozen=True)
class DigestItem:
    date_key: str
    text: str
    source_kind: SourceKind
    source_id: str


@dataclass(frozen=True)
class DigestTheme:
    key: str  # t1, t2, ... — 순서가 FE 색을 정하므로 안정적이어야 한다
    name: str
    summary: str
    items: list[DigestItem] = field(default_factory=list)


@dataclass(frozen=True)
class StructuredDigest:
    summary: str
    themes: list[DigestTheme] = field(default_factory=list)
    version: int = STRUCTURE_VERSION

    # ── 직렬화 (JSONB / API) ────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "summary": self.summary,
            "themes": [
                {
                    "key": t.key,
                    "name": t.name,
                    "summary": t.summary,
                    "items": [
                        {
                            "dateKey": i.date_key,
                            "text": i.text,
                            "source": {"kind": i.source_kind, "id": i.source_id},
                        }
                        for i in t.items
                    ],
                }
                for t in self.themes
            ],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "StructuredDigest":
        return cls(
            version=int(d.get("version", STRUCTURE_VERSION)),
            summary=d.get("summary", ""),
            themes=[
                DigestTheme(
                    key=t["key"],
                    name=t["name"],
                    summary=t.get("summary", ""),
                    items=[
                        DigestItem(
                            date_key=i["dateKey"],
                            text=i["text"],
                            source_kind=i["source"]["kind"],
                            source_id=i["source"]["id"],
                        )
                        for i in t.get("items", [])
                    ],
                )
                for t in d.get("themes", [])
            ],
        )

    # ── 파생 값 ─────────────────────────────────────────────────────────────

    def source_ids(self) -> set[tuple[SourceKind, str]]:
        return {(i.source_kind, i.source_id) for t in self.themes for i in t.items}

    def period(self) -> tuple[str, str] | None:
        """항목 날짜의 (최소, 최대). 항목이 없으면 None."""
        dates = [i.date_key for t in self.themes for i in t.items]
        return (min(dates), max(dates)) if dates else None

    def recent_items(self, before_or_on: str, limit: int = 5) -> list[tuple[DigestItem, str]]:
        """오늘(포함) 이전 항목을 날짜 내림차순으로 — (항목, theme key)."""
        pairs = [(i, t.key) for t in self.themes for i in t.items if i.date_key <= before_or_on]
        pairs.sort(key=lambda p: p[0].date_key, reverse=True)
        return pairs[:limit]

    def to_markdown(self) -> str:
        """`## 큰 주제` / 요약 / `- M/D 한 일`. 첫 줄은 전체 한 줄 요약."""
        lines = [self.summary]
        for t in self.themes:
            lines += ["", f"## {t.name}"]
            if t.summary:
                lines.append(t.summary)
            for i in t.items:
                d = date.fromisoformat(i.date_key)
                lines.append(f"- {d.month}/{d.day} {i.text}")
        return "\n".join(lines).strip()


def _clip(text: Any, limit: int) -> str:
    s = " ".join(str(text or "").split())
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


def normalize(raw: dict[str, Any], sources: dict[str, SourceRef]) -> StructuredDigest:
    """모델 출력(raw) → 검증·정리된 구조.

    - 모르는 표식을 가리키는 항목은 버린다. 항목이 하나도 안 남은 큰 주제도 버린다.
    - 항목 날짜는 근거의 날짜로 채운다(모델이 준 날짜는 쓰지 않는다).
    - 큰 주제는 가장 이른 항목 날짜 순으로 정렬하고 key 를 t1 부터 다시 매긴다.
    - 상한: 큰 주제 6개, 큰 주제당 항목 12개, 이름 20자, 요약 100자, 항목 120자.
      넘치면 **최신 쪽을 남긴다** — 증분 정리에서 새로 들어온 근거가 잘리지 않게.
    - 같은 근거가 여러 큰 주제에 들어가는 것은 허용한다.
    """
    themes: list[tuple[str, DigestTheme]] = []
    for raw_theme in raw.get("themes") or []:
        if not isinstance(raw_theme, dict):
            continue
        items: list[DigestItem] = []
        seen: set[tuple[str, str]] = set()
        for raw_item in raw_theme.get("items") or []:
            if not isinstance(raw_item, dict):
                continue
            ref = sources.get(str(raw_item.get("source") or "").strip())
            text = _clip(raw_item.get("text"), MAX_ITEM_TEXT)
            if ref is None or not text or (ref.id, text) in seen:
                continue
            seen.add((ref.id, text))
            items.append(DigestItem(ref.date_key, text, ref.kind, ref.id))
        if not items:
            continue
        items.sort(key=lambda i: i.date_key)
        items = items[-MAX_ITEMS_PER_THEME:]
        name = _clip(raw_theme.get("name"), MAX_THEME_NAME) or items[0].text[:MAX_THEME_NAME]
        theme = DigestTheme(
            key="", name=name, summary=_clip(raw_theme.get("summary"), MAX_SUMMARY), items=items
        )
        themes.append((items[0].date_key, theme))

    if len(themes) > MAX_THEMES:
        # 가장 최근 항목이 늦은 큰 주제부터 남긴다(오래 손대지 않은 주제가 밀려난다).
        themes.sort(key=lambda p: p[1].items[-1].date_key, reverse=True)
        themes = themes[:MAX_THEMES]
    themes.sort(key=lambda p: p[0])
    ordered = [
        DigestTheme(key=f"t{n}", name=t.name, summary=t.summary, items=t.items)
        for n, (_, t) in enumerate(themes, start=1)
    ]
    return StructuredDigest(summary=_clip(raw.get("summary"), MAX_SUMMARY), themes=ordered)
