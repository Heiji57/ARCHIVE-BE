from app.shared.domain.utils.period import today_in_tz
from app.todo.application.dtos.queries import GetTodosFilteredQuery
from app.todo.domain.models.todo import Todo
from app.todo.domain.repositories.repository import ITodoRepository


class GetTodosFilteredUseCase:
    """보이는 기간과 무관한 조회 — 지난 마감, 마감 기간, Google 보내기 실패.

    실제 row 만 본다(가상 반복 인스턴스는 펼치지 않음). 끝나지 않은 매일 반복 시리즈의
    지난 회차를 전부 "지난 마감"으로 펼치면 수백 개가 쏟아지기 때문 — 사용자가 손댄
    회차(예외 row)만 대상이다.
    """

    def __init__(self, todo_repo: ITodoRepository) -> None:
        self._todo_repo = todo_repo

    async def execute(self, query: GetTodosFilteredQuery) -> list[Todo]:
        today = query.today or today_in_tz(query.tz).isoformat()
        overdue_before = today if query.overdue else None
        return await self._todo_repo.find_filtered(
            query.user_id,
            overdue_before=overdue_before,
            due_from=query.due_from,
            due_to=query.due_to,
            push_status=query.push_status,
            calendar_ids=query.calendar_ids,
            include_default_calendar=query.include_default_calendar,
            offset=(query.page - 1) * query.size,
            limit=query.size,
        )
