from datetime import date

from fastapi import HTTPException


def parse_date_range(
    from_date: str | None, to_date: str | None, max_days: int
) -> tuple[date, date] | None:
    """from/to 쿼리 파라미터 공통 검증. 둘 다 없으면 None(호출부가 각자 기본 동작 처리).

    ISO 형식이 아니거나(422) 범위가 max_days 를 초과하면(422) HTTPException 을 던진다.
    """
    if not (from_date and to_date):
        return None
    try:
        f, t = date.fromisoformat(from_date), date.fromisoformat(to_date)
    except ValueError:
        raise HTTPException(status_code=422, detail="날짜 형식이 올바르지 않습니다 (YYYY-MM-DD).")
    if (t - f).days > max_days:
        raise HTTPException(status_code=422, detail=f"날짜 범위는 최대 {max_days}일입니다.")
    return f, t
