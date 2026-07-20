import re

from pydantic import BaseModel, Field, field_validator, model_validator


class LinkRepositoryRequest(BaseModel):
    github_repo_id: int = Field(gt=0, alias="githubRepoId")

    model_config = {"populate_by_name": True}


class UpdateRepositoryRequest(BaseModel):
    commit_read_enabled: bool = Field(alias="commitReadEnabled")

    model_config = {"populate_by_name": True}


_DAILY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_WEEKLY_RE = re.compile(r"^\d{4}-\d{2}-W[1-6]$")
_MONTHLY_RE = re.compile(r"^\d{4}-\d{2}$")
_ANNUAL_RE = re.compile(r"^\d{4}$")

_PATTERN_BY_TYPE = {
    "DAILY": _DAILY_RE,
    "WEEKLY": _WEEKLY_RE,
    "MONTHLY": _MONTHLY_RE,
    "ANNUAL": _ANNUAL_RE,
}


class PushRetrospectiveRequest(BaseModel):
    period_type: str = Field(alias="periodType")
    period_key: str = Field(alias="periodKey")
    content_markdown: str = Field(alias="contentMarkdown", min_length=1, max_length=1_000_000)

    model_config = {"populate_by_name": True}

    @field_validator("period_type", mode="before")
    @classmethod
    def normalize_period_type(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("periodType must be a string.")
        normalized = v.strip().upper()
        if normalized not in _PATTERN_BY_TYPE:
            raise ValueError(
                "periodType must be one of DAILY, WEEKLY, MONTHLY, ANNUAL."
            )
        return normalized

    @model_validator(mode="after")
    def validate_period_key_format(self) -> "PushRetrospectiveRequest":
        pattern = _PATTERN_BY_TYPE[self.period_type]
        if not pattern.fullmatch(self.period_key):
            raise ValueError(
                f"periodKey does not match {self.period_type} format."
            )
        return self
