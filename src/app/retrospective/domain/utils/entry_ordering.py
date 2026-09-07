from datetime import date

from app.retrospective.domain.models.journal_entry import JournalEntry
from app.retrospective.domain.models.retro_summary import RetroSummary


def content_date(item: JournalEntry | RetroSummary) -> date:
    """merge 정렬 기준 — journal entry 는 date_key(회고 대상 일자), summary 는
    period_start(요약 대상 기간 시작일). created_at(레코드 생성 시각) 대신 이걸
    쓰는 이유: 나중에 백필한 과거 회고가 오늘 날짜로 최상단에 뜨면 안 되므로,
    단일 타입 조회(date_key/period_start 정렬)와 동일한 기준으로 통일한다."""
    if isinstance(item, JournalEntry):
        return date.fromisoformat(item.date_key)
    return item.period_start


def content_order_key(item: JournalEntry | RetroSummary) -> tuple[date, str]:
    """(content_date, id) — 통합 페이지네이션용 결정적 정렬 키.

    id tie-break 가 없으면 같은 날짜의 항목들 사이 순서가 비결정적이라
    페이지 경계에서 항목이 누락되거나 중복된다."""
    return content_date(item), item.id


def merge_sorted_desc(
    entries: list[JournalEntry], summaries: list[RetroSummary]
) -> list[JournalEntry | RetroSummary]:
    """daily(journal_entries) + weekly/monthly/annual(retro_summaries) 를 합쳐
    (날짜 DESC, id DESC) 로 정렬한다 ("전체" 뷰 병합 공통 로직). UNION 결과
    전체에 `ORDER BY date_key DESC, id DESC` 를 건 것과 같은 순서다.

    각 소스도 같은 기준으로 상위 N개를 가져와야 "각 소스 상위 N개면 전역 상위
    N개를 항상 커버한다"는 성질이 성립한다 — 소스 정렬과 병합 정렬의 기준이
    어긋나면 페이지 경계에서 틀린 집합을 뽑는다. 그래서 find_page /
    find_by_folder_page 의 ORDER BY 에도 id tie-break 가 함께 들어가 있다."""
    return sorted([*entries, *summaries], key=content_order_key, reverse=True)
