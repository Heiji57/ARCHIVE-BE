from dataclasses import dataclass
from datetime import date

from app.retrospective.domain.models.journal_entry import JournalEntry
from app.retrospective.domain.models.retro_summary import RetroSummary
from app.retrospective.domain.models.value_objects import SummaryType

_TYPE_KO = {
    SummaryType.WEEKLY: "주간",
    SummaryType.MONTHLY: "월간",
    SummaryType.ANNUAL: "연간",
}


@dataclass(frozen=True)
class WeekSection:
    """Monthly 하이브리드 프롬프트의 한 주 구간.

    - weekly_summary 있으면 그 요약을 본문으로 사용. supplementary_entries 는
      weekly 갱신 이후 추가된 entry 들(방식 B 보강) — 비어있을 수 있음.
    - weekly_summary 가 None 이면 supplementary_entries 가 그 주의 raw entry 들.
    """
    index: int
    period_start: date
    period_end: date
    weekly_summary: RetroSummary | None
    supplementary_entries: list[JournalEntry]


@dataclass(frozen=True)
class MonthSection:
    """Annual 하이브리드 프롬프트의 한 달 구간.

    - monthly_summary 있으면 그 요약 사용.
    - 없으면 그 달의 weekly_summaries 로 보강. 둘 다 비면 빈 섹션.
    """
    month: int
    monthly_summary: RetroSummary | None
    weekly_summaries: list[RetroSummary]


def build_prompt_from_entries(summary_type: SummaryType, entries: list[JournalEntry]) -> str:
    """Weekly 요약 — 그 주의 entry 들을 직접 AI 에 feed."""
    period_name = _TYPE_KO[summary_type]

    if not entries:
        entries_text = "(이 기간에 작성된 회고 기록이 없습니다.)"
    else:
        entries_text = "\n\n".join(
            f"[{e.date_key} / {e.retro_type.value}] {e.title}\n{e.content}"
            for e in entries
        )

    return f"""당신은 개발자의 회고 기록을 분석하고 인사이트를 도출하는 전문가입니다.
아래는 개발자의 {period_name} 회고 기록입니다. 이를 바탕으로 핵심 내용을 추출해 아래 JSON 형식으로만 응답하세요.

회고 기록:
{entries_text}

응답 형식 (JSON만 출력, 한국어로 작성):
{{
  "achievements": ["이 기간에 달성한 성과나 완료한 작업들 (최대 5개)"],
  "challenges": ["어려웠던 점이나 해결해야 할 과제들 (최대 5개)"],
  "learnings": ["배운 것들, 깨달은 점들 (최대 5개)"],
  "next_focus": ["다음 기간에 집중할 것들 (최대 5개)"]
}}"""


def build_prompt_monthly_hybrid(weeks: list[WeekSection]) -> str:
    """Monthly 요약 — 주 단위로 weekly summary 또는 entries 혼합."""
    if not weeks:
        body = "(이 달에 작성된 회고 기록이 없습니다.)"
    else:
        sections: list[str] = []
        for w in weeks:
            sections.append(_render_week_section(w))
        body = "\n\n".join(sections)

    return f"""당신은 개발자의 회고 기록을 분석하고 인사이트를 도출하는 전문가입니다.
아래는 한 달간 주차별 회고 기록입니다. 일부 주는 사전에 생성된 주간 요약본으로, 일부 주는 일일 회고 원문으로 제공됩니다.
각 주의 비중을 동등하게 두고 종합하여 월간 핵심 내용을 추출해 아래 JSON 형식으로만 응답하세요.

월간 회고 기록:
{body}

응답 형식 (JSON만 출력, 한국어로 작성):
{{
  "achievements": ["이 달에 달성한 성과나 완료한 작업들 (최대 5개)"],
  "challenges": ["어려웠던 점이나 해결해야 할 과제들 (최대 5개)"],
  "learnings": ["배운 것들, 깨달은 점들 (최대 5개)"],
  "next_focus": ["다음 달에 집중할 것들 (최대 5개)"]
}}"""


def build_prompt_annual_hybrid(months: list[MonthSection]) -> str:
    """Annual 요약 — 월 단위로 monthly summary 또는 weekly summaries 혼합."""
    if not months:
        body = "(이 해에 작성된 회고 기록이 없습니다.)"
    else:
        sections: list[str] = []
        for m in months:
            sections.append(_render_month_section(m))
        body = "\n\n".join(sections)

    return f"""당신은 개발자의 회고 기록을 분석하고 인사이트를 도출하는 전문가입니다.
아래는 한 해의 월별 회고 기록입니다. 일부 월은 사전에 생성된 월간 요약본으로, 일부 월은 그 달의 주간 요약들로 제공됩니다.
각 월의 비중을 동등하게 두고 종합하여 연간 핵심 내용을 추출해 아래 JSON 형식으로만 응답하세요.

연간 회고 기록:
{body}

응답 형식 (JSON만 출력, 한국어로 작성):
{{
  "achievements": ["이 해에 달성한 성과나 완료한 작업들 (최대 5개)"],
  "challenges": ["어려웠던 점이나 해결해야 할 과제들 (최대 5개)"],
  "learnings": ["배운 것들, 깨달은 점들 (최대 5개)"],
  "next_focus": ["다음 해에 집중할 것들 (최대 5개)"]
}}"""


def _render_week_section(w: WeekSection) -> str:
    header = f"[Week {w.index} ({w.period_start} ~ {w.period_end})"

    if w.weekly_summary and w.weekly_summary.content:
        block = (
            f"{header} — 주간 요약]\n"
            + _render_summary_content(w.weekly_summary)
        )
        if w.supplementary_entries:
            extra = "\n\n".join(
                f"  - [{e.date_key}] {e.title}\n    {e.content}"
                for e in w.supplementary_entries
            )
            block += (
                f"\n\n[Week {w.index} — 주간 요약 생성 이후 추가된 일일 회고]\n{extra}"
            )
        return block

    if w.supplementary_entries:
        entries_text = "\n\n".join(
            f"[{e.date_key} / {e.retro_type.value}] {e.title}\n{e.content}"
            for e in w.supplementary_entries
        )
        return (
            f"{header} — 주간 요약 미생성, 일일 회고 원문 첨부]\n{entries_text}"
        )

    return f"{header} — 데이터 없음]"


def _render_month_section(m: MonthSection) -> str:
    header = f"[Month {m.month:02d}"

    if m.monthly_summary and m.monthly_summary.content:
        return f"{header} — 월간 요약]\n" + _render_summary_content(m.monthly_summary)

    valid_weeklies = [s for s in m.weekly_summaries if s.content]
    if valid_weeklies:
        weekly_blocks = "\n\n".join(
            f"  - [{s.period_start} ~ {s.period_end}]\n"
            f"    성과: {_join(s.content.achievements)}\n"
            f"    어려움: {_join(s.content.challenges)}\n"
            f"    배움: {_join(s.content.learnings)}\n"
            f"    다음 집중: {_join(s.content.next_focus)}"
            for s in valid_weeklies
        )
        return (
            f"{header} — 월간 요약 미생성, 주간 요약 {len(valid_weeklies)}개로 보강]\n{weekly_blocks}"
        )

    return f"{header} — 데이터 없음, 스킵]"


def _render_summary_content(summary: RetroSummary) -> str:
    c = summary.content
    return (
        f"성과: {_join(c.achievements)}\n"
        f"어려움: {_join(c.challenges)}\n"
        f"배움: {_join(c.learnings)}\n"
        f"다음 집중: {_join(c.next_focus)}"
    )


def _join(items) -> str:
    return ", ".join(items) if items else "(없음)"
