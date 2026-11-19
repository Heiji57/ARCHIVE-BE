"""AI 모듈이 다른 모듈의 기능을 쓰는 좁은 포트.

AI 는 할 일·회고 테이블에 직접 쓰지 않는다 — 쓰기는 할 일 모듈의 묶음 수정 규칙을 그대로
타야 한다(반복 회차, Google push, 임베딩). 그렇다고 응용 계층이 다른 모듈의 유스케이스를
직접 부르지도 않도록(develop.md §13), 필요한 동작만 여기 Protocol 로 정의하고 구현은
`ai/infrastructure/adapters/` 가 맡는다.
"""

from datetime import date, datetime
from typing import Any, Protocol

from app.ai.domain.models.agent import ModelMessage, ModelTurn, ToolSpec
from app.ai.domain.models.snapshots import TodoSnapshot


class TodoPort(Protocol):
    async def list_on(self, user_id: str, date_key: str) -> list[TodoSnapshot]:
        """그날의 할 일(반복 회차 펼침, 취소 회차 제외)."""
        ...

    async def list_overdue(
        self, user_id: str, tz: str, limit: int, today: str | None = None
    ) -> list[TodoSnapshot]: ...

    async def get(self, user_id: str, todo_id: str) -> TodoSnapshot | None:
        """가상 반복 회차 id 도 받는다."""
        ...

    async def apply_patch(self, user_id: str, todo_id: str, patch: dict[str, Any]) -> str:
        """PATCH /todos/{id} 규칙으로 바꾼다. 바뀐 할 일 id(가상 회차면 새 예외 row id)."""
        ...

    async def list_range(self, user_id: str, from_key: str, to_key: str) -> list[TodoSnapshot]:
        """기간의 할 일(반복 회차 펼침). Google 일정도 pull-sync 로 할 일이 되어 함께 나온다."""
        ...

    async def create(
        self,
        user_id: str,
        title: str,
        date_key: str,
        start_time: datetime | None,
        end_time: datetime | None,
        timezone: str | None,
    ) -> str:
        """POST /todos 규칙으로 만든다(기본 캘린더·Google 자동 보내기 설정 포함). 새 id."""
        ...

    async def delete(self, user_id: str, todo_id: str) -> None:
        """DELETE /todos/{id}(이번 회차) 규칙으로 지운다(Google 일정 정리 포함)."""
        ...


class CommitPort(Protocol):
    async def messages_on(self, user_id: str, day: date) -> list[str]:
        """그날 본인 커밋 메시지. GitHub 미연결·실패면 빈 목록."""
        ...

    async def list_range(self, user_id: str, from_day: date, to_day: date) -> list[dict[str, Any]]:
        """기간 본인 커밋 [{date, repository, message}]. 미연결·실패면 빈 목록."""
        ...


class RetroPort(Protocol):
    async def search(self, user_id: str, query: str, limit: int) -> list[dict[str, Any]]:
        """회고 검색 [{id, date, type, title, excerpt}]."""
        ...

    async def create_draft(self, user_id: str, date_key: str, content: str) -> str:
        """그날 일간 회고를 만든다(POST /entries 규칙). 새 id. 이미 있으면 그 규칙의 오류."""
        ...

    async def get(self, user_id: str, entry_id: str) -> dict[str, Any] | None:
        """{id, content} 또는 없으면 None."""
        ...

    async def delete(self, user_id: str, entry_id: str) -> None: ...


class ChatModelPort(Protocol):
    async def generate(
        self, system: str, history: list[ModelMessage], tools: list[ToolSpec]
    ) -> ModelTurn:
        """한 차례. 도구를 부르려면 calls 를, 끝났으면 text 를 돌려준다."""
        ...


class EventSink(Protocol):
    async def emit(self, event: dict[str, Any]) -> None:
        """대화 SSE 이벤트 — step(진행 문장) · delta(답 글자) · proposal · done · error."""
        ...
