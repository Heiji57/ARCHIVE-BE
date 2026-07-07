from pydantic import BaseModel

from app.retrospective.presentation.responses.responses import EntryResponse
from app.search.application.use_cases.global_search import GlobalSearchResult
from app.todo.presentation.responses.responses import TodoResponse


class GlobalSearchResponse(BaseModel):
    todos: list[TodoResponse]
    entries: list[EntryResponse]

    model_config = {"populate_by_name": True}

    @classmethod
    def from_result(cls, result: GlobalSearchResult) -> "GlobalSearchResponse":
        return cls(
            todos=[TodoResponse.from_entity(t) for t in result.todos],
            entries=[EntryResponse.from_entity(e) for e in result.entries],
        )
