from pydantic import BaseModel

from app.retrospective.presentation.responses.responses import EntryResponse
from app.search.application.use_cases.global_search import GlobalSearchResult
from app.todo.presentation.responses.responses import TodoResponse
from app.topic.domain.models.topic import Topic


class TopicSearchItem(BaseModel):
    id: str
    name: str
    description: str

    @classmethod
    def from_entity(cls, topic: Topic) -> "TopicSearchItem":
        return cls(id=topic.id, name=topic.name, description=topic.description)


class GlobalSearchResponse(BaseModel):
    todos: list[TodoResponse]
    entries: list[EntryResponse]
    topics: list[TopicSearchItem]

    model_config = {"populate_by_name": True}

    @classmethod
    def from_result(cls, result: GlobalSearchResult) -> "GlobalSearchResponse":
        return cls(
            todos=[TodoResponse.from_entity(t) for t in result.todos],
            entries=[EntryResponse.from_entity(e) for e in result.entries],
            topics=[TopicSearchItem.from_entity(t) for t in result.topics],
        )
