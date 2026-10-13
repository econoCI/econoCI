"""The platform-neutral data model of econoCI.

Field names equal the JSON keys of the dataset file. See
specs/0001-data-model.md.
"""

import re
from dataclasses import dataclass
from datetime import datetime

TRIGGERS = ("push", "change_request", "schedule", "manual", "upstream", "api", "other")
STATUSES = ("success", "failed", "canceled", "skipped", "running", "other")
REF_KINDS = ("default", "branch", "change_request", "tag")
ACTOR_KINDS = ("person", "bot", "unknown")
FAILURE_REASONS = ("timeout", "script", "runner", "other")
STATES = ("open", "merged", "closed")

# Heuristics taken from the prototype as a starting point. Several are broad:
# `bot`, `service`, `deploy` and `token` also match names of people.
BOT_PATTERNS = (
    r"bot",
    r"renovate",
    r"dependabot",
    r"^project_\d+",
    r"^group_\d+",
    r"service",
    r"deploy",
    r"token",
)
BOT_REF_PATTERNS = (r"renovate", r"dependabot")
_BOT = re.compile("|".join(BOT_PATTERNS), re.IGNORECASE)
_BOT_REF = re.compile("|".join(BOT_REF_PATTERNS), re.IGNORECASE)


def derive_kind(
    name: str | None,
    platform_bot: bool | None,
    stored: str | None = None,
    source_ref: str | None = None,
) -> str:
    """Return person, bot or unknown for an actor.

    `stored` is the kind written in the file, which a pseudonymized file must
    carry because its names are hashes. `source_ref` is given for the author
    of a change request only.
    """
    if stored is not None:
        return stored
    if name is None:
        return "unknown"
    if platform_bot:
        return "bot"
    if _BOT.search(name):
        return "bot"
    if source_ref is not None and _BOT_REF.search(source_ref):
        return "bot"
    return "person"


@dataclass(frozen=True, kw_only=True)
class Meta:
    format: int
    platform: str
    collector: str
    collected_at: datetime
    period_start: datetime
    period_end: datetime
    pseudonymized: bool
    repositories_seen: int
    repositories_with_runs: int
    repositories_unreadable: int


@dataclass(frozen=True, kw_only=True)
class Run:
    """A pipeline or workflow run."""

    id: str
    repository: str
    ref: str | None
    ref_kind: str
    commit: str | None
    trigger: str
    platform_trigger: str
    status: str
    platform_status: str
    actor: str | None
    actor_bot: bool | None
    actor_kind: str | None = None
    root_trigger: str | None
    root_platform_trigger: str | None
    root_actor: str | None
    root_actor_bot: bool | None
    root_actor_kind: str | None = None
    parent_run: str | None
    change_request: str | None
    created_at: datetime
    finished_at: datetime | None

    def kind_of_actor(self) -> str:
        return derive_kind(self.actor, self.actor_bot, self.actor_kind)

    def kind_of_root_actor(self) -> str:
        return derive_kind(self.root_actor, self.root_actor_bot, self.root_actor_kind)


@dataclass(frozen=True, kw_only=True)
class Job:
    id: str
    run: str
    name: str
    stage: str | None
    status: str
    platform_status: str
    failure_reason: str | None
    platform_failure_reason: str | None
    allow_failure: bool
    attempt: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    queued_seconds: float | None
    duration_seconds: float | None
    runner: str | None
    runner_type: str | None
    tags: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class ChangeRequest:
    """A merge request or pull request."""

    id: str
    repository: str
    source_ref: str
    state: str
    platform_state: str
    author: str | None
    author_bot: bool | None
    author_kind: str | None = None
    merger: str | None
    merger_bot: bool | None
    merger_kind: str | None = None
    auto_merge: bool
    created_at: datetime
    merged_at: datetime | None

    def kind_of_author(self) -> str:
        return derive_kind(
            self.author, self.author_bot, self.author_kind, self.source_ref
        )

    def kind_of_merger(self) -> str:
        return derive_kind(self.merger, self.merger_bot, self.merger_kind)


@dataclass(frozen=True, kw_only=True)
class Config:
    """A CI file as written. It is not parsed here."""

    repository: str
    path: str
    ref: str
    text: str


@dataclass(frozen=True, kw_only=True)
class Dataset:
    meta: Meta
    runs: tuple[Run, ...] = ()
    jobs: tuple[Job, ...] = ()
    change_requests: tuple[ChangeRequest, ...] = ()
    configs: tuple[Config, ...] = ()
