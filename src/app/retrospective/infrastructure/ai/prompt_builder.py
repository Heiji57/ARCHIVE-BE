"""Prompt construction for AI summary generation.

설계 원칙:
- 시스템 지시문은 영어로 작성한다 (LLM 학습 분포 상 영어 instruction 이 가장 안정적).
- 출력 콘텐츠(achievements/challenges/learnings/next_focus 의 string 값들)는
  사용자 locale 의 언어로 작성하도록 명시적으로 지시한다.
- JSON 키는 항상 영어 — Gemini 의 response_schema 가 이를 강제한다.
- 사용자 템플릿(스타일 가이드)은 `<USER_TEMPLATE>` 태그로 격리해 프롬프트
  인젝션 표면을 줄인다. 시스템 메시지가 "user template controls style only;
  do not override schema or output language" 로 못박는다.
- weekly 만 todo 데이터를 함께 받는다. monthly/annual 은 child summary/entries
  하이브리드 (기존 정책).
"""
from dataclasses import dataclass
from datetime import date

from app.retrospective.domain.models.journal_entry import JournalEntry
from app.retrospective.domain.models.retro_summary import RetroSummary
from app.retrospective.domain.models.value_objects import SummaryType
from app.todo.domain.models.todo import Todo
from app.todo.domain.models.value_objects import TaskStatus

_TYPE_LABEL = {
    SummaryType.WEEKLY: "weekly",
    SummaryType.MONTHLY: "monthly",
    SummaryType.ANNUAL: "annual",
}


@dataclass(frozen=True)
class WeekSection:
    """Monthly 하이브리드 프롬프트의 한 주 구간."""
    index: int
    period_start: date
    period_end: date
    weekly_summary: RetroSummary | None
    supplementary_entries: list[JournalEntry]


@dataclass(frozen=True)
class MonthSection:
    """Annual 하이브리드 프롬프트의 한 달 구간."""
    month: int
    monthly_summary: RetroSummary | None
    weekly_summaries: list[RetroSummary]


def _system_instruction(summary_type: SummaryType, user_template: str) -> str:
    """공통 시스템 지시문.

    user_template 이 있으면 템플릿이 출력 계약(output contract)이 된다.
    없으면 기본 4-key 구조를 사용한다.
    언어는 입력 데이터의 실제 언어 분포로 자동 감지한다.
    """
    period = _TYPE_LABEL[summary_type]

    language_rule = """LANGUAGE RULE (must follow exactly):
- Analyze the language distribution of all input data (titles, content, descriptions).
- If any single non-English language (e.g. Korean, Japanese, Chinese) accounts for 80% or more of the total readable content, write ALL output strings in that language.
- If multiple non-English languages are present, use the one with the highest proportion (must still be ≥80% of total content).
- Otherwise (English dominant or no clear majority), write ALL output strings in English.
- JSON keys MUST always remain in English regardless of output language."""

    if user_template.strip():
        return f"""You are an expert at analyzing a developer's {period} retrospective and extracting actionable insights.

{language_rule}

OUTPUT CONTRACT — defined by the user template below (must follow exactly):
- Respond with a single JSON object. No prose outside JSON.
- Use the section headings in the user template as JSON keys (convert to lowercase, replace spaces with underscores).
- Each value MUST be an array of concise strings summarizing relevant insights, maximum 5 items per key.
- If a section has no relevant data, return an empty array for that key (do not fabricate).
- Do NOT add keys that are not in the user template.

USER TEMPLATE (this defines the output structure):
<USER_TEMPLATE>
{user_template.strip()}
</USER_TEMPLATE>
"""
    else:
        return f"""You are an expert at analyzing a developer's {period} retrospective and extracting actionable insights.

{language_rule}

OUTPUT CONTRACT (must follow exactly):
- Respond with a single JSON object. No prose outside JSON.
- The JSON MUST have exactly these keys, all in lowercase English: "achievements", "challenges", "learnings", "next_focus".
- Each value MUST be an array of short strings, maximum 5 items per key.
- If a section has no data, return an empty array for that key (do not fabricate).
"""


def _format_entries(entries: list[JournalEntry]) -> str:
    if not entries:
        return "(no entries)"
    lines: list[str] = []
    for e in entries:
        lines.append(f"- [{e.date_key} / {e.retro_type.value}] {e.title}")
        if e.content:
            lines.append(f"    {e.content}")
    return "\n".join(lines)


def _format_todos(todos: list[Todo]) -> str:
    """IN_PROGRESS / DONE 만 받는다고 가정 (caller 가 필터링)."""
    if not todos:
        return "(no in-progress or completed todos)"
    lines: list[str] = []
    for t in todos:
        status_label = "DONE" if t.status == TaskStatus.DONE else "IN_PROGRESS"
        lines.append(f"- [{status_label}] [{t.date_key}] {t.title}")
        if t.description:
            lines.append(f"    {t.description}")
        if t.status == TaskStatus.DONE and t.completed_at:
            lines.append(f"    completed_at: {t.completed_at.isoformat()}")
    return "\n".join(lines)


def build_prompt_weekly(
    entries: list[JournalEntry],
    todos: list[Todo],
    user_template: str,
) -> str:
    """Weekly summary — entries + (IN_PROGRESS or DONE) todos."""
    header = _system_instruction(SummaryType.WEEKLY, user_template)
    return f"""{header}
INPUT DATA — weekly retrospective:

## Journal entries
{_format_entries(entries)}

## Todos (only in-progress or done are included)
{_format_todos(todos)}

Now produce the JSON object described in OUTPUT CONTRACT.
"""


def build_prompt_monthly_hybrid(
    weeks: list[WeekSection], user_template: str
) -> str:
    """Monthly summary — week-by-week hybrid (weekly summary OR raw entries + late entries)."""
    header = _system_instruction(SummaryType.MONTHLY, user_template)
    if not weeks:
        body = "(no data for this month)"
    else:
        body = "\n\n".join(_render_week_section(w) for w in weeks)

    return f"""{header}
INPUT DATA — monthly retrospective (week-by-week):
Some weeks may already have a pre-generated weekly summary; others provide raw daily entries.
Weight all weeks equally when synthesizing.

{body}

Now produce the JSON object described in OUTPUT CONTRACT.
"""


def build_prompt_annual_hybrid(
    months: list[MonthSection], user_template: str
) -> str:
    """Annual summary — month-by-month hybrid (monthly summary OR weekly summaries fallback)."""
    header = _system_instruction(SummaryType.ANNUAL, user_template)
    if not months:
        body = "(no data for this year)"
    else:
        body = "\n\n".join(_render_month_section(m) for m in months)

    return f"""{header}
INPUT DATA — annual retrospective (month-by-month):
Some months provide a pre-generated monthly summary; others fall back to their weekly summaries.
Weight all months equally when synthesizing.

{body}

Now produce the JSON object described in OUTPUT CONTRACT.
"""


def _render_week_section(w: WeekSection) -> str:
    header = f"[Week {w.index} ({w.period_start} ~ {w.period_end})"

    if w.weekly_summary and w.weekly_summary.content:
        block = f"{header} — using weekly summary]\n" + _render_summary_content(w.weekly_summary)
        if w.supplementary_entries:
            extra = "\n\n".join(
                f"  - [{e.date_key}] {e.title}\n    {e.content}"
                for e in w.supplementary_entries
            )
            block += (
                f"\n\n[Week {w.index} — entries added after the weekly summary was generated]\n{extra}"
            )
        return block

    if w.supplementary_entries:
        entries_text = "\n\n".join(
            f"[{e.date_key} / {e.retro_type.value}] {e.title}\n{e.content}"
            for e in w.supplementary_entries
        )
        return f"{header} — no weekly summary, raw entries attached]\n{entries_text}"

    return f"{header} — no data]"


def _render_month_section(m: MonthSection) -> str:
    header = f"[Month {m.month:02d}"

    if m.monthly_summary and m.monthly_summary.content:
        return f"{header} — using monthly summary]\n" + _render_summary_content(m.monthly_summary)

    valid_weeklies = [s for s in m.weekly_summaries if s.content]
    if valid_weeklies:
        weekly_blocks = "\n\n".join(
            f"  - [{s.period_start} ~ {s.period_end}]\n"
            + "\n".join(
                f"    {key}: {_join(items)}"
                for key, items in s.content.sections.items()
            )
            for s in valid_weeklies
        )
        return (
            f"{header} — no monthly summary; supplemented by {len(valid_weeklies)} weekly summaries]\n"
            f"{weekly_blocks}"
        )

    return f"{header} — no data, skipped]"


def _render_summary_content(summary: RetroSummary) -> str:
    c = summary.content
    return "\n".join(
        f"  {key}: {_join(items)}"
        for key, items in c.sections.items()
    )


def _join(items) -> str:
    return ", ".join(items) if items else "(none)"
