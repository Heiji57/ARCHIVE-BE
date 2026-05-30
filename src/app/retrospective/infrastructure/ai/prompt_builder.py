from app.retrospective.domain.models.journal_entry import JournalEntry
from app.retrospective.domain.models.retro_summary import RetroSummary
from app.retrospective.domain.models.value_objects import SummaryType

_TYPE_KO = {
    SummaryType.WEEKLY: "주간",
    SummaryType.MONTHLY: "월간",
    SummaryType.ANNUAL: "연간",
}

_CHILD_TYPE_KO = {
    SummaryType.MONTHLY: "주간",
    SummaryType.ANNUAL: "월간",
}


def build_prompt(summary_type: SummaryType, entries: list[JournalEntry]) -> str:
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


def build_prompt_from_summaries(summary_type: SummaryType, child_summaries: list[RetroSummary]) -> str:
    period_name = _TYPE_KO[summary_type]
    child_period_name = _CHILD_TYPE_KO[summary_type]

    if not child_summaries or not any(s.content for s in child_summaries):
        summaries_text = f"(이 기간에 완료된 {child_period_name} 요약이 없습니다.)"
    else:
        parts = []
        for s in child_summaries:
            if s.content:
                parts.append(
                    f"[{s.period_start} ~ {s.period_end}]\n"
                    f"성과: {', '.join(s.content.achievements)}\n"
                    f"어려움: {', '.join(s.content.challenges)}\n"
                    f"배움: {', '.join(s.content.learnings)}\n"
                    f"다음 집중: {', '.join(s.content.next_focus)}"
                )
        summaries_text = "\n\n".join(parts)

    return f"""당신은 개발자의 회고 기록을 분석하고 인사이트를 도출하는 전문가입니다.
아래는 개발자의 {child_period_name} 회고 요약들입니다. 이를 종합하여 {period_name} 핵심 내용을 추출해 아래 JSON 형식으로만 응답하세요.

{child_period_name} 요약 기록:
{summaries_text}

응답 형식 (JSON만 출력, 한국어로 작성):
{{
  "achievements": ["이 기간에 달성한 성과나 완료한 작업들 (최대 5개)"],
  "challenges": ["어려웠던 점이나 해결해야 할 과제들 (최대 5개)"],
  "learnings": ["배운 것들, 깨달은 점들 (최대 5개)"],
  "next_focus": ["다음 기간에 집중할 것들 (최대 5개)"]
}}"""
