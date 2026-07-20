from dataclasses import dataclass


@dataclass(frozen=True)
class LinkRepositoryCommand:
    user_id: str
    github_repo_id: int


@dataclass(frozen=True)
class SyncAllRepositoriesCommand:
    user_id: str


@dataclass(frozen=True)
class UnlinkRepositoryCommand:
    user_id: str
    repository_id: str


@dataclass(frozen=True)
class PushRetrospectiveCommand:
    user_id: str
    period_type: str   # "DAILY" | "WEEKLY" | "MONTHLY" | "ANNUAL"
    period_key: str    # DAILY: "2026-06-12", WEEKLY: "2026-06-W2", MONTHLY: "2026-06", ANNUAL: "2026"
    content_markdown: str
