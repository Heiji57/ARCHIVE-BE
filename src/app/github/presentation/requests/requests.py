from pydantic import BaseModel, Field


class LinkRepositoryRequest(BaseModel):
    github_repo_id: int = Field(gt=0, alias="githubRepoId")

    model_config = {"populate_by_name": True}
