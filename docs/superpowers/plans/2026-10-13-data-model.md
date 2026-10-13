# Data Model and Dataset File Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The records of an econoCI dataset exist as Python types, and a dataset file can be written and read back with strict validation.

**Architecture:** `src/econoci/model.py` holds frozen dataclasses and the person-or-bot derivation. `src/econoci/dataset.py` holds one schema table per record kind, which drives both reading (with validation) and writing (in a fixed key order). `write` validates through the same code as `read`, so an invalid dataset never reaches the disk.

**Tech Stack:** Python 3.11 standard library (`dataclasses`, `gzip`, `json`), `pytest`, `ruff`, `nox` through `uvx nox`.

**Spec:** `specs/0001-data-model.md`. Read it before starting.

## Global Constraints

- `src/econoci/` uses the standard library only and runs on Python 3.11.
- Tests run on Python 3.11 and 3.14.
- Test data is synthetic, with invented names. No real dataset file in the repository.
- Write the failing test first and watch it fail.
- JSON keys, enum values and their order are exactly those in the spec's tables.
- A file that does not match the spec raises `DatasetError` naming the file and the line. Nothing is skipped silently.
- One implementation commit for this plan, plus one for the spec and plan. Each message carries the `AI-assisted` block and is shown for approval before committing.
- Prose rules: no em dashes, American English.

## Review Focus

1. **A collection that was interrupted**, leaving a truncated gzip file. `DatasetError`, not a traceback from `gzip` or `zlib`. (Task 2)
2. **A large file.** The reader goes through the file line by line and does not load the text as one string. (Task 2)
3. **Timestamps ending in `Z`**, as GitLab writes them. Accepted and equal to the `+00:00` form. (Task 2)
4. **A path given as a string**, not a `Path`. Accepted by `read` and `write`. (Task 2)
5. **A dataset built in code with a wrong value**, such as a trigger outside the list. `write` raises `DatasetError` and leaves no file behind. (Task 2)

## File Structure

| File | Responsibility |
| --- | --- |
| `src/econoci/__init__.py` | Package marker. |
| `src/econoci/model.py` | Enum value lists, the five record types, `Dataset`, `derive_kind`. No I/O. |
| `src/econoci/dataset.py` | Schema tables, `read`, `write`, `dumps`, `DatasetError`. |
| `tests/test_model.py` | Person-or-bot derivation. |
| `tests/test_dataset.py` | Round trip, determinism, every error case. |
| `pyproject.toml`, `noxfile.py` | `src` on the test path; tests on 3.11 and 3.14. |

---

### Task 1: The model

**Files:**
- Create: `src/econoci/__init__.py`, `src/econoci/model.py`
- Test: `tests/test_model.py`
- Modify: `pyproject.toml`, `noxfile.py`

**Interfaces:**
- Produces: tuples `TRIGGERS`, `STATUSES`, `REF_KINDS`, `ACTOR_KINDS`, `FAILURE_REASONS`, `STATES`, `BOT_PATTERNS`; `derive_kind(name, platform_bot, stored=None, source_ref=None) -> str`; keyword-only frozen dataclasses `Meta`, `Run`, `Job`, `ChangeRequest`, `Config`, `Dataset` whose field names equal the JSON keys of the spec; methods `Run.kind_of_actor()`, `Run.kind_of_root_actor()`, `ChangeRequest.kind_of_author()`, `ChangeRequest.kind_of_merger()`.

- [ ] **Step 1: Put `src` on the test path and test on both Python versions**

In `pyproject.toml`, replace `pythonpath = ["tools"]` with `pythonpath = ["src", "tools"]`.

In `noxfile.py`, replace the decorator of `tests`:

```python
@nox.session(python=["3.11", "3.14"])
def tests(session):
    session.install("pytest")
    session.run("pytest", *session.posargs)
```

- [ ] **Step 2: Write the failing tests**

`tests/test_model.py`:

```python
from datetime import UTC, datetime

import pytest
from econoci import model

T = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)


def run(**changes):
    values = {
        "id": "r1",
        "repository": "acme/shop",
        "ref": "main",
        "ref_kind": "default",
        "commit": "abc123",
        "trigger": "push",
        "platform_trigger": "push",
        "status": "success",
        "platform_status": "success",
        "actor": "pat",
        "actor_bot": False,
        "root_trigger": "push",
        "root_platform_trigger": "push",
        "root_actor": "pat",
        "root_actor_bot": False,
        "parent_run": None,
        "change_request": None,
        "created_at": T,
        "finished_at": T,
    }
    return model.Run(**{**values, **changes})


def change_request(**changes):
    values = {
        "id": "c1",
        "repository": "acme/shop",
        "source_ref": "feature/cart",
        "state": "merged",
        "platform_state": "merged",
        "author": "pat",
        "author_bot": False,
        "merger": "sam",
        "merger_bot": False,
        "auto_merge": False,
        "created_at": T,
        "merged_at": T,
    }
    return model.ChangeRequest(**{**values, **changes})


def test_a_stored_kind_wins_over_everything():
    assert model.derive_kind("renovate-bot", True, stored="person") == "person"
    assert model.derive_kind(None, None, stored="bot") == "bot"


def test_no_name_is_unknown():
    assert model.derive_kind(None, None) == "unknown"
    assert model.derive_kind(None, True) == "unknown"


def test_the_platform_flag_makes_a_bot():
    assert model.derive_kind("pat", True) == "bot"


def test_an_ordinary_name_is_a_person():
    assert model.derive_kind("pat", False) == "person"
    assert model.derive_kind("pat", None) == "person"


@pytest.mark.parametrize(
    ("matching", "not_matching"),
    [
        ("build-bot", "bob"),
        ("Renovate-Runner", "renata"),
        ("dependabot", "dependable"),
        ("project_123_x", "my_project_123"),
        ("group_45_x", "subgroup_45"),
        ("shop-service", "servus"),
        ("deployer", "deputy"),
        ("ci-token-user", "tolkien"),
    ],
)
def test_bot_patterns(matching, not_matching):
    assert model.derive_kind(matching, False) == "bot"
    assert model.derive_kind(not_matching, False) == "person"


def test_every_bot_pattern_has_a_case():
    assert len(model.BOT_PATTERNS) == 8


@pytest.mark.parametrize("ref", ["renovate/pytest-9.x", "Dependabot/pip/urllib3"])
def test_a_bot_branch_makes_the_author_a_bot(ref):
    assert model.derive_kind("pat", False, source_ref=ref) == "bot"
    assert model.derive_kind("pat", False, source_ref="feature/cart") == "person"


def test_run_kinds_are_derived():
    record = run(actor="pat", root_actor="renovate-bot", root_actor_bot=None)
    assert record.kind_of_actor() == "person"
    assert record.kind_of_root_actor() == "bot"


def test_run_kinds_prefer_the_stored_value():
    record = run(actor="u_1f2e3d", actor_kind="bot", root_actor_kind="person")
    assert record.kind_of_actor() == "bot"
    assert record.kind_of_root_actor() == "person"


def test_run_with_unresolved_root_has_an_unknown_root_actor():
    record = run(trigger="upstream", root_trigger=None, root_actor=None)
    assert record.kind_of_root_actor() == "unknown"


def test_change_request_author_uses_the_source_ref_and_merger_does_not():
    record = change_request(source_ref="renovate/pytest-9.x")
    assert record.kind_of_author() == "bot"
    assert record.kind_of_merger() == "person"


def test_change_request_without_merger():
    record = change_request(merger=None, merger_bot=None, merged_at=None)
    assert record.kind_of_merger() == "unknown"


def test_records_are_immutable():
    record = run()
    with pytest.raises(AttributeError):
        record.trigger = "schedule"


def test_dataset_groups_records():
    meta = model.Meta(
        format=1,
        platform="gitlab",
        collector="test 0",
        collected_at=T,
        period_start=T,
        period_end=T,
        pseudonymized=False,
        repositories_seen=1,
        repositories_with_runs=1,
        repositories_unreadable=0,
    )
    dataset = model.Dataset(meta=meta, runs=(run(),))
    assert dataset.runs[0].id == "r1"
    assert dataset.jobs == ()
```

- [ ] **Step 3: Run the tests and watch them fail**

Run: `uvx nox -s tests-3.14 -- tests/test_model.py`
Expected: collection error, `ModuleNotFoundError: No module named 'econoci'`

- [ ] **Step 4: Write the package**

`src/econoci/__init__.py`:

```python
"""econoCI: find wasted CI runner time and say what to change."""
```

`src/econoci/model.py`:

```python
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

# Heuristics taken from the prototype as a starting point. The second and third
# to last are broad and can flag a person.
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
```

- [ ] **Step 5: Run the tests on both Python versions**

Run: `uvx nox -s tests`
Expected: all pass on 3.11 and 3.14, including the tests under `tests/tools/`.

---

### Task 2: Reading and writing the file

**Files:**
- Create: `src/econoci/dataset.py`
- Test: `tests/test_dataset.py`

**Interfaces:**
- Consumes from `econoci.model`: the value tuples and the six dataclasses of Task 1.
- Produces: `DatasetError`, `FORMAT = 1`, `read(path: Path | str) -> Dataset`, `write(dataset: Dataset, path: Path | str) -> None`, `dumps(dataset: Dataset) -> str`.

- [ ] **Step 1: Write the failing tests**

`tests/test_dataset.py`:

```python
import gzip
import json
from datetime import UTC, datetime

import pytest
from econoci import dataset, model

STAMP = "2026-01-02T12:00:00+00:00"


def meta(**changes):
    return {
        "kind": "meta",
        "format": 1,
        "platform": "gitlab",
        "collector": "test 0",
        "collected_at": STAMP,
        "period_start": "2025-12-03T12:00:00+00:00",
        "period_end": STAMP,
        "pseudonymized": False,
        "repositories_seen": 3,
        "repositories_with_runs": 2,
        "repositories_unreadable": 1,
        **changes,
    }


def run(**changes):
    return {
        "kind": "run",
        "id": "r1",
        "repository": "acme/shop",
        "ref": "main",
        "ref_kind": "default",
        "commit": "abc123",
        "trigger": "push",
        "platform_trigger": "push",
        "status": "success",
        "platform_status": "success",
        "actor": "pat",
        "actor_bot": False,
        "root_trigger": "push",
        "root_platform_trigger": "push",
        "root_actor": "pat",
        "root_actor_bot": False,
        "parent_run": None,
        "change_request": None,
        "created_at": STAMP,
        "finished_at": STAMP,
        **changes,
    }


def child_run(**changes):
    return run(
        id="r2",
        trigger="upstream",
        platform_trigger="parent_pipeline",
        root_trigger="schedule",
        root_platform_trigger="schedule",
        root_actor="nightly-bot",
        root_actor_bot=True,
        parent_run="r1",
        **changes,
    )


def job(**changes):
    return {
        "kind": "job",
        "id": "j1",
        "run": "r1",
        "name": "unit tests",
        "stage": "test",
        "status": "failed",
        "platform_status": "failed",
        "failure_reason": "timeout",
        "platform_failure_reason": "job_execution_timeout",
        "allow_failure": False,
        "attempt": 2,
        "created_at": STAMP,
        "started_at": STAMP,
        "finished_at": STAMP,
        "queued_seconds": 4.5,
        "duration_seconds": 3600,
        "runner": "runner-7",
        "runner_type": "instance_type",
        "tags": ["docker", "large"],
        **changes,
    }


def change_request(**changes):
    return {
        "kind": "change_request",
        "id": "c1",
        "repository": "acme/shop",
        "source_ref": "feature/cart",
        "state": "merged",
        "platform_state": "merged",
        "author": "pat",
        "author_bot": False,
        "merger": "sam",
        "merger_bot": False,
        "auto_merge": True,
        "created_at": STAMP,
        "merged_at": STAMP,
        **changes,
    }


def config(**changes):
    return {
        "kind": "config",
        "repository": "acme/shop",
        "path": ".gitlab-ci.yml",
        "ref": "main",
        "text": "test:\n  script: [make test]\n",
        **changes,
    }


def save(tmp_path, rows, name="data.jsonl.gz"):
    path = tmp_path / name
    text = "".join(
        row if isinstance(row, str) else json.dumps(row) + "\n" for row in rows
    )
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write(text)
    return path


def without(row, key):
    return {k: v for k, v in row.items() if k != key}


FULL = [
    meta(),
    run(change_request="c1"),
    child_run(),
    run(
        id="r3",
        ref=None,
        commit=None,
        status="running",
        platform_status="running",
        actor=None,
        actor_bot=None,
        root_actor=None,
        root_actor_bot=None,
        finished_at=None,
    ),
    job(),
    job(
        id="j2",
        stage=None,
        status="skipped",
        platform_status="skipped",
        failure_reason=None,
        platform_failure_reason=None,
        attempt=1,
        started_at=None,
        finished_at=None,
        queued_seconds=None,
        duration_seconds=None,
        runner=None,
        runner_type=None,
        tags=[],
    ),
    change_request(),
    change_request(
        id="c2",
        state="open",
        platform_state="opened",
        author=None,
        author_bot=None,
        merger=None,
        merger_bot=None,
        auto_merge=False,
        merged_at=None,
    ),
    config(),
]


def test_read_returns_every_record(tmp_path):
    data = dataset.read(save(tmp_path, FULL))
    assert data.meta.platform == "gitlab"
    assert [record.id for record in data.runs] == ["r1", "r2", "r3"]
    assert [record.id for record in data.jobs] == ["j1", "j2"]
    assert [record.id for record in data.change_requests] == ["c1", "c2"]
    assert data.configs[0].text.startswith("test:")
    assert data.runs[0].created_at == datetime(2026, 1, 2, 12, 0, tzinfo=UTC)
    assert data.jobs[0].tags == ("docker", "large")
    assert data.jobs[0].duration_seconds == 3600
    assert data.runs[2].actor is None


def test_write_then_read_gives_the_same_dataset(tmp_path):
    first = dataset.read(save(tmp_path, FULL))
    dataset.write(first, tmp_path / "copy.jsonl.gz")
    assert dataset.read(tmp_path / "copy.jsonl.gz") == first


def test_paths_may_be_strings(tmp_path):
    first = dataset.read(str(save(tmp_path, FULL)))
    dataset.write(first, str(tmp_path / "copy.jsonl.gz"))
    assert dataset.read(str(tmp_path / "copy.jsonl.gz")) == first


def test_writing_twice_gives_the_same_bytes(tmp_path):
    data = dataset.read(save(tmp_path, FULL))
    dataset.write(data, tmp_path / "one.jsonl.gz")
    dataset.write(data, tmp_path / "two.jsonl.gz")
    one = (tmp_path / "one.jsonl.gz").read_bytes()
    assert one == (tmp_path / "two.jsonl.gz").read_bytes()


def test_keys_are_written_in_the_order_of_the_specification(tmp_path):
    data = dataset.read(save(tmp_path, FULL))
    lines = [json.loads(line) for line in dataset.dumps(data).splitlines()]
    assert [line["kind"] for line in lines] == [
        "meta",
        "run",
        "run",
        "run",
        "job",
        "job",
        "change_request",
        "change_request",
        "config",
    ]
    assert list(lines[1]) == list(run())
    assert list(lines[4]) == list(job())
    assert list(lines[6]) == list(change_request())
    assert list(lines[8]) == list(config())


def test_a_raw_file_leaves_the_kind_keys_out(tmp_path):
    data = dataset.read(save(tmp_path, FULL))
    assert "_kind" not in dataset.dumps(data).replace("ref_kind", "")


def test_timestamps_ending_in_z_are_accepted(tmp_path):
    rows = [meta(collected_at="2026-01-02T12:00:00Z")]
    data = dataset.read(save(tmp_path, rows))
    assert data.meta.collected_at == datetime(2026, 1, 2, 12, 0, tzinfo=UTC)


def test_dangling_parent_and_change_request_are_allowed(tmp_path):
    rows = [meta(), child_run(parent_run="gone", change_request="gone too")]
    data = dataset.read(save(tmp_path, rows))
    assert data.runs[0].parent_run == "gone"


def test_child_run_with_unresolved_root_is_accepted(tmp_path):
    rows = [
        meta(),
        child_run(
            root_trigger=None,
            root_platform_trigger=None,
            root_actor=None,
            root_actor_bot=None,
            parent_run=None,
        ),
    ]
    assert dataset.read(save(tmp_path, rows)).runs[0].root_trigger is None


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("root_trigger", "schedule"),
        ("root_platform_trigger", "schedule"),
        ("root_actor", "sam"),
        ("root_actor_bot", True),
    ],
)
def test_top_level_run_must_repeat_its_own_values_as_root(tmp_path, key, value):
    path = save(tmp_path, [meta(), run(**{key: value})])
    with pytest.raises(dataset.DatasetError, match=rf"data.jsonl.gz:2: .*{key}"):
        dataset.read(path)


@pytest.mark.parametrize(
    ("builder", "key", "values"),
    [
        (run, "ref_kind", model.REF_KINDS),
        (run, "status", model.STATUSES),
        (job, "status", model.STATUSES),
        (job, "failure_reason", model.FAILURE_REASONS),
        (change_request, "state", model.STATES),
    ],
)
def test_every_listed_value_is_accepted(tmp_path, builder, key, values):
    for value in values:
        rows = [meta(), run(), builder(**{key: value})]
        if builder is run:
            rows = [meta(), builder(**{key: value})]
        dataset.read(save(tmp_path, rows))


@pytest.mark.parametrize("trigger", model.TRIGGERS)
def test_every_trigger_is_accepted(tmp_path, trigger):
    row = run(trigger=trigger, root_trigger=trigger)
    if trigger == "upstream":
        row = child_run()
    assert dataset.read(save(tmp_path, [meta(), row])).runs[0].trigger == trigger


@pytest.mark.parametrize(
    ("row", "key"),
    [
        (run(ref_kind="fork"), "ref_kind"),
        (run(trigger="cron"), "trigger"),
        (run(status="green"), "status"),
        (child_run(root_trigger="cron"), "root_trigger"),
        (job(status="green"), "status"),
        (job(failure_reason="flaky"), "failure_reason"),
        (change_request(state="draft"), "state"),
        (run(actor_kind="robot"), "actor_kind"),
    ],
)
def test_a_value_outside_the_list_is_rejected(tmp_path, row, key):
    rows = [meta(), run(id="r1")] if row["kind"] == "job" else [meta()]
    path = save(tmp_path, [*rows, row])
    line = len(rows) + 1
    with pytest.raises(dataset.DatasetError, match=rf"data.jsonl.gz:{line}: {key} "):
        dataset.read(path)


def test_a_stored_kind_is_read_and_written(tmp_path):
    rows = [meta(), run(actor_kind="bot", root_actor_kind="bot")]
    data = dataset.read(save(tmp_path, rows))
    assert data.runs[0].kind_of_actor() == "bot"
    assert '"actor_kind":"bot"' in dataset.dumps(data)


def pseudonymized_rows():
    return [
        meta(pseudonymized=True),
        run(
            actor="u_1f2e3d",
            root_actor="u_1f2e3d",
            actor_kind="person",
            root_actor_kind="person",
        ),
        change_request(author_kind="person", merger_kind="bot"),
    ]


def test_a_pseudonymized_file_with_every_kind_is_accepted(tmp_path):
    data = dataset.read(save(tmp_path, pseudonymized_rows()))
    assert data.change_requests[0].kind_of_merger() == "bot"


@pytest.mark.parametrize(
    ("index", "key"),
    [(1, "actor_kind"), (1, "root_actor_kind"), (2, "author_kind"), (2, "merger_kind")],
)
def test_a_pseudonymized_file_without_a_kind_is_rejected(tmp_path, index, key):
    rows = pseudonymized_rows()
    rows[index] = without(rows[index], key)
    path = save(tmp_path, rows)
    with pytest.raises(dataset.DatasetError, match=rf":{index + 1}: {key} "):
        dataset.read(path)


def test_file_that_is_not_gzip(tmp_path):
    path = tmp_path / "plain.jsonl.gz"
    path.write_text(json.dumps(meta()) + "\n", encoding="utf-8")
    with pytest.raises(dataset.DatasetError, match="plain.jsonl.gz: cannot read"):
        dataset.read(path)


def test_file_that_does_not_exist(tmp_path):
    with pytest.raises(dataset.DatasetError, match="missing.jsonl.gz: cannot read"):
        dataset.read(tmp_path / "missing.jsonl.gz")


def test_truncated_file(tmp_path):
    path = save(tmp_path, [meta(), *[run(id=f"r{n}") for n in range(200)]])
    path.write_bytes(path.read_bytes()[:-20])
    with pytest.raises(dataset.DatasetError, match="data.jsonl.gz"):
        dataset.read(path)


def test_empty_file(tmp_path):
    with pytest.raises(dataset.DatasetError, match="no meta record"):
        dataset.read(save(tmp_path, []))


@pytest.mark.parametrize(
    ("rows", "line", "message"),
    [
        ([meta(), "{broken\n"], 2, "not JSON"),
        ([meta(), "[1, 2]\n"], 2, "not a JSON object"),
        ([meta(), "\n", run()], 2, "empty line"),
        ([run()], 1, "first line must be the meta record"),
        ([meta(), meta()], 2, "second meta record"),
        ([meta(format=2)], 1, "format 2 is not supported"),
        ([meta(format=2, extra="x")], 1, "format 2 is not supported"),
        ([meta(), {"kind": "artifact"}], 2, "unknown kind 'artifact'"),
        ([meta(), {"id": "r1"}], 2, "unknown kind None"),
        ([meta(), without(run(), "trigger")], 2, "trigger is missing"),
        ([meta(), run(color="blue")], 2, "unknown key 'color'"),
        ([meta(), run(id=7)], 2, "id is not a string"),
        ([meta(), run(repository=None)], 2, "repository must not be null"),
        ([meta(), run(actor_bot="no")], 2, "actor_bot is not a boolean"),
        ([meta(), run(), job(attempt=True)], 3, "attempt is not an integer"),
        ([meta(), run(), job(attempt=1.5)], 3, "attempt is not an integer"),
        ([meta(), run(), job(queued_seconds="4")], 3, "queued_seconds is not a number"),
        ([meta(), run(), job(tags="docker")], 3, "tags is not a list of strings"),
        ([meta(), run(), job(tags=["docker", 3])], 3, "tags is not a list of strings"),
        ([meta(), run(created_at="yesterday")], 2, "created_at is not a timestamp"),
        ([meta(), run(created_at="2026-01-02T12:00:00")], 2, "created_at has no UTC"),
        ([meta(), run(), run()], 3, "duplicate run id 'r1'"),
        ([meta(), run(), job(), job()], 4, "duplicate job id 'j1'"),
        (
            [meta(), change_request(), change_request()],
            3,
            "duplicate change_request id 'c1'",
        ),
        ([meta(), job()], 2, "run 'r1', which is not in the file"),
    ],
)
def test_reading_errors_name_the_line(tmp_path, rows, line, message):
    path = save(tmp_path, rows)
    with pytest.raises(dataset.DatasetError) as caught:
        dataset.read(path)
    assert f"data.jsonl.gz:{line}: " in str(caught.value)
    assert message in str(caught.value)


def test_a_job_may_come_before_its_run(tmp_path):
    data = dataset.read(save(tmp_path, [meta(), job(), run()]))
    assert data.jobs[0].run == "r1"


def test_write_refuses_an_invalid_dataset_and_leaves_no_file(tmp_path):
    good = dataset.read(save(tmp_path, [meta(), run()]))
    bad_run = model.Run(**{**vars(good.runs[0]), "trigger": "cron"})
    bad = model.Dataset(meta=good.meta, runs=(bad_run,))
    target = tmp_path / "bad.jsonl.gz"
    with pytest.raises(dataset.DatasetError, match="trigger"):
        dataset.write(bad, target)
    assert not target.exists()
```

- [ ] **Step 2: Run the tests and watch them fail**

Run: `uvx nox -s tests-3.14 -- tests/test_dataset.py`
Expected: collection error, `ImportError: cannot import name 'dataset' from 'econoci'`

- [ ] **Step 3: Write `src/econoci/dataset.py`**

```python
"""Read and write econoCI dataset files.

A dataset file is gzip-compressed JSON Lines. One schema table per record kind
drives both directions, so the reader's checks and the writer's key order
cannot drift apart. See specs/0001-data-model.md.
"""

import gzip
import json
import zlib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from econoci.model import (
    ACTOR_KINDS,
    FAILURE_REASONS,
    REF_KINDS,
    STATES,
    STATUSES,
    TRIGGERS,
    ChangeRequest,
    Config,
    Dataset,
    Job,
    Meta,
    Run,
)

FORMAT = 1


class DatasetError(Exception):
    """A dataset does not match the specification."""


@dataclass(frozen=True)
class Field:
    key: str
    type: str  # string, integer, boolean, number, timestamp or strings
    nullable: bool = False  # the key is present and may be null
    optional: bool = False  # the key may be absent
    values: tuple[str, ...] | None = None


def _text(key: str, **options) -> Field:
    return Field(key, "string", **options)


def _flag(key: str, **options) -> Field:
    return Field(key, "boolean", **options)


def _time(key: str, **options) -> Field:
    return Field(key, "timestamp", **options)


def _kind(key: str) -> Field:
    return Field(key, "string", optional=True, values=ACTOR_KINDS)


SCHEMAS: dict[str, tuple[type, tuple[Field, ...]]] = {
    "meta": (
        Meta,
        (
            Field("format", "integer"),
            _text("platform"),
            _text("collector"),
            _time("collected_at"),
            _time("period_start"),
            _time("period_end"),
            _flag("pseudonymized"),
            Field("repositories_seen", "integer"),
            Field("repositories_with_runs", "integer"),
            Field("repositories_unreadable", "integer"),
        ),
    ),
    "run": (
        Run,
        (
            _text("id"),
            _text("repository"),
            _text("ref", nullable=True),
            _text("ref_kind", values=REF_KINDS),
            _text("commit", nullable=True),
            _text("trigger", values=TRIGGERS),
            _text("platform_trigger"),
            _text("status", values=STATUSES),
            _text("platform_status"),
            _text("actor", nullable=True),
            _flag("actor_bot", nullable=True),
            _kind("actor_kind"),
            _text("root_trigger", nullable=True, values=TRIGGERS),
            _text("root_platform_trigger", nullable=True),
            _text("root_actor", nullable=True),
            _flag("root_actor_bot", nullable=True),
            _kind("root_actor_kind"),
            _text("parent_run", nullable=True),
            _text("change_request", nullable=True),
            _time("created_at"),
            _time("finished_at", nullable=True),
        ),
    ),
    "job": (
        Job,
        (
            _text("id"),
            _text("run"),
            _text("name"),
            _text("stage", nullable=True),
            _text("status", values=STATUSES),
            _text("platform_status"),
            _text("failure_reason", nullable=True, values=FAILURE_REASONS),
            _text("platform_failure_reason", nullable=True),
            _flag("allow_failure"),
            Field("attempt", "integer"),
            _time("created_at"),
            _time("started_at", nullable=True),
            _time("finished_at", nullable=True),
            Field("queued_seconds", "number", nullable=True),
            Field("duration_seconds", "number", nullable=True),
            _text("runner", nullable=True),
            _text("runner_type", nullable=True),
            Field("tags", "strings"),
        ),
    ),
    "change_request": (
        ChangeRequest,
        (
            _text("id"),
            _text("repository"),
            _text("source_ref"),
            _text("state", values=STATES),
            _text("platform_state"),
            _text("author", nullable=True),
            _flag("author_bot", nullable=True),
            _kind("author_kind"),
            _text("merger", nullable=True),
            _flag("merger_bot", nullable=True),
            _kind("merger_kind"),
            _flag("auto_merge"),
            _time("created_at"),
            _time("merged_at", nullable=True),
        ),
    ),
    "config": (
        Config,
        (
            _text("repository"),
            _text("path"),
            _text("ref"),
            _text("text"),
        ),
    ),
}

TYPE_NAMES = {
    "string": "a string",
    "integer": "an integer",
    "boolean": "a boolean",
    "number": "a number",
    "timestamp": "a timestamp",
    "strings": "a list of strings",
}

# A pseudonymized file has hashes for names, so the kinds cannot be derived.
KINDS_OF = {
    "run": ("actor_kind", "root_actor_kind"),
    "change_request": ("author_kind", "merger_kind"),
}

# What a run with no parent repeats in its root fields.
ROOT_OF = (
    ("root_trigger", "trigger"),
    ("root_platform_trigger", "platform_trigger"),
    ("root_actor", "actor"),
    ("root_actor_bot", "actor_bot"),
)


def _has_type(field: Field, value: object) -> bool:
    if field.type in ("string", "timestamp"):
        return isinstance(value, str)
    if field.type == "boolean":
        return isinstance(value, bool)
    if field.type == "integer":
        return type(value) is int
    if field.type == "number":
        return type(value) in (int, float)
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _decode(field: Field, value: object, where: str) -> object:
    if value is None:
        if field.nullable:
            return None
        raise DatasetError(f"{where}: {field.key} must not be null")
    if not _has_type(field, value):
        raise DatasetError(f"{where}: {field.key} is not {TYPE_NAMES[field.type]}")
    if field.values is not None and value not in field.values:
        raise DatasetError(f"{where}: {field.key} has the unknown value {value!r}")
    if field.type == "timestamp":
        try:
            stamp = datetime.fromisoformat(value)
        except ValueError as error:
            raise DatasetError(f"{where}: {field.key} is not a timestamp") from error
        if stamp.tzinfo is None:
            raise DatasetError(f"{where}: {field.key} has no UTC offset")
        return stamp
    if field.type == "strings":
        return tuple(value)
    return value


def _record(row: dict, where: str) -> tuple[str, object]:
    kind = row.get("kind")
    if kind not in SCHEMAS:
        raise DatasetError(f"{where}: unknown kind {kind!r}")
    record_type, fields = SCHEMAS[kind]
    extra = sorted(set(row) - {"kind"} - {field.key for field in fields})
    if extra:
        raise DatasetError(f"{where}: unknown key {extra[0]!r}")
    values = {}
    for field in fields:
        if field.key in row:
            values[field.key] = _decode(field, row[field.key], where)
        elif field.optional:
            values[field.key] = None
        else:
            raise DatasetError(f"{where}: {field.key} is missing")
    return kind, record_type(**values)


def _check(kind: str, record: object, meta: Meta, where: str) -> None:
    if meta.pseudonymized:
        for key in KINDS_OF.get(kind, ()):
            if getattr(record, key) is None:
                raise DatasetError(
                    f"{where}: {key} is missing in a pseudonymized file"
                )
    if kind == "run" and record.parent_run is None and record.trigger != "upstream":
        for root_key, own_key in ROOT_OF:
            if getattr(record, root_key) != getattr(record, own_key):
                raise DatasetError(
                    f"{where}: {root_key} differs from {own_key} "
                    "although the run has no parent"
                )


def _parse(lines: Iterable[str], source: str) -> Dataset:
    meta: Meta | None = None
    records: dict[str, list] = {kind: [] for kind in SCHEMAS if kind != "meta"}
    ids: dict[str, set[str]] = {"run": set(), "job": set(), "change_request": set()}
    job_lines: list[tuple[str, Job]] = []
    for number, line in enumerate(lines, 1):
        where = f"{source}:{number}"
        if not line.strip():
            raise DatasetError(f"{where}: empty line")
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise DatasetError(f"{where}: not JSON ({error.msg})") from error
        if not isinstance(row, dict):
            raise DatasetError(f"{where}: not a JSON object")
        if number == 1:
            if row.get("kind") != "meta":
                raise DatasetError(f"{where}: the first line must be the meta record")
            # Checked before the keys: a later format may have other keys.
            if row.get("format") != FORMAT:
                raise DatasetError(
                    f"{where}: format {row.get('format')} is not supported, "
                    f"this version reads format {FORMAT}"
                )
            meta = _record(row, where)[1]
            continue
        kind, record = _record(row, where)
        if kind == "meta":
            raise DatasetError(f"{where}: a second meta record")
        if kind in ids:
            if record.id in ids[kind]:
                raise DatasetError(f"{where}: duplicate {kind} id {record.id!r}")
            ids[kind].add(record.id)
        _check(kind, record, meta, where)
        records[kind].append(record)
        if kind == "job":
            job_lines.append((where, record))
    if meta is None:
        raise DatasetError(f"{source}: no meta record, the file is empty")
    for where, job in job_lines:
        if job.run not in ids["run"]:
            raise DatasetError(
                f"{where}: the job names the run {job.run!r}, which is not in the file"
            )
    return Dataset(
        meta=meta,
        runs=tuple(records["run"]),
        jobs=tuple(records["job"]),
        change_requests=tuple(records["change_request"]),
        configs=tuple(records["config"]),
    )


def read(path: Path | str) -> Dataset:
    """Read a dataset file, or raise DatasetError naming the file and the line."""
    path = Path(path)
    try:
        with gzip.open(path, "rt", encoding="utf-8", newline="\n") as handle:
            return _parse((line.rstrip("\n") for line in handle), str(path))
    except (OSError, EOFError, zlib.error, UnicodeDecodeError) as error:
        raise DatasetError(f"{path}: cannot read the file ({error})") from error


def _row(kind: str, record: object) -> dict:
    row: dict[str, object] = {"kind": kind}
    for field in SCHEMAS[kind][1]:
        value = getattr(record, field.key)
        if value is None and field.optional:
            continue
        if isinstance(value, datetime):
            value = value.isoformat()
        elif isinstance(value, tuple):
            value = list(value)
        row[field.key] = value
    return row


def dumps(dataset: Dataset) -> str:
    """Return the dataset as JSON Lines, in the order the specification gives."""
    groups = (
        ("meta", (dataset.meta,)),
        ("run", dataset.runs),
        ("job", dataset.jobs),
        ("change_request", dataset.change_requests),
        ("config", dataset.configs),
    )
    return "".join(
        json.dumps(_row(kind, record), separators=(",", ":"), ensure_ascii=False)
        + "\n"
        for kind, records in groups
        for record in records
    )


def write(dataset: Dataset, path: Path | str) -> None:
    """Write a dataset file.

    An invalid dataset raises DatasetError and nothing is written.
    """
    text = dumps(dataset)
    # Only a line feed ends a record; splitlines would also split inside a text.
    _parse(text.split("\n")[:-1], "dataset")
    with (
        open(path, "wb") as raw,
        # No file name and no time in the header, so the bytes are reproducible.
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as handle,
    ):
        handle.write(text.encode("utf-8"))
```

- [ ] **Step 4: Run tests and lint**

Run: `uvx nox -s tests lint`
Expected: all pass on 3.11 and 3.14. If `ruff format --check` fails, run `uvx ruff format .` and rerun.

- [ ] **Step 5: Commit**

Two commits, each shown for approval first: the spec and this plan, then the implementation (`src/`, `tests/test_model.py`, `tests/test_dataset.py`, `pyproject.toml`, `noxfile.py`).
