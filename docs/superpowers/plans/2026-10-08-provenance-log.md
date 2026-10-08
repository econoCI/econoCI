# AI Provenance in Commit Messages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every AI-assisted commit in econoCI carries an approved `AI-assisted` block, with a helper that lists the prompts since the last commit and a check that fails when the block is missing.

**Architecture:** Two standalone scripts under `tools/`, each one file with pure functions and a thin `main`. `check_commit_messages.py` reads commit messages through `git log`. `prompts_since_commit.py` reads Claude Code's local session files and prints to the terminal. `nox` runs tests, lint and the check.

**Tech Stack:** Python standard library, tested on 3.14, `pytest`, `ruff`, `nox` with the uv backend, run through `uvx nox`.

**Spec:** `specs/provenance-log.md`. Read it before starting.

## Global Constraints

- Standard library only in `tools/`. No network calls, no language model.
- Tests and lint run on Python 3.14 only. `requires-python = ">=3.11"` and the ruff target describe the product to come; a 3.11 test run is added when the collector lands.
- Scripts live under `tools/`, not `src/econoci/`.
- Test data is synthetic. No real transcript text, no customer, project or person names, no tokens in `tests/`.
- Write the failing test first and watch it fail.
- The block has exactly these four fields, in this order: `AI-assisted`, `Prompts`, `Output`, `Human`. Continuation lines are indented by two spaces.
- The check covers every commit after `8076110`.
- The helper prints to the terminal only. It writes no file.
- Every commit in this plan is AI-assisted: stage the changes, draft the full message with the block (`Prompts` from the prompts since the last commit, `Output` from `git diff --cached`), and show it to Aarno with `git diff --cached --stat`, naming every change no prompt asked for and every prompt that left no trace in the diff. Commit only after explicit approval, with the message exactly as approved. Never commit on an implied yes.
- Commit trailers, after the block and a blank line: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and the `Claude-Session:` line the session provides.
- Prose rules: no em dashes, American English.
- Work on branch `provenance-commit-block`, cut from `main`. The repository has no remote.

## Review Focus

Inputs the spec does not spell out and that are likely to occur:

1. **The helper runs while the session is still writing its transcript.** An unfinished last line is skipped. A broken line anywhere else is an error. (Task 2)
2. **A stale session file from an older Claude Code version with unknown record types.** A file last modified before the cut-off is not read, so it cannot block the helper. (Task 2)
3. **`Co-authored-by:` in lower case**, as GitHub writes it. Matched without regard to case. (Task 1)
4. **A bad revision range or an empty one.** A bad range gives a one-line error and exit code 2, no traceback. An empty range passes and reports 0 commits. (Task 1)
5. **`--since` without a UTC offset.** Rejected with a message, because it cannot be compared with transcript timestamps. (Task 2)

## File Structure

| File | Responsibility |
| --- | --- |
| `pyproject.toml` | Project metadata, pytest and ruff settings. No dependencies. |
| `noxfile.py` | Sessions `tests`, `lint`, `commit_messages`. |
| `tools/check_commit_messages.py` | Decide whether a commit message is AI-assisted and which block fields it lacks; run that over a revision range. |
| `tools/prompts_since_commit.py` | Read session files, extract what the person typed or answered, print it from a cut-off onward. |
| `tests/tools/test_check_commit_messages.py` | Tests for the check. |
| `tests/tools/test_prompts_since_commit.py` | Tests for the helper. |
| `README.md`, `CLAUDE.md` | The rule, in words. |

---

### Task 0: Branch and commit the specification

**Files:**
- Commit: `specs/provenance-log.md`, `docs/superpowers/plans/2026-10-08-provenance-log.md`

- [ ] **Step 1: Create the branch**

```bash
git switch -c provenance-commit-block
```

- [ ] **Step 2: Draft the commit message and show it for approval**

Draft, to be adjusted to what was actually asked:

```text
Specify AI provenance in commit messages

The specification for marking AI-assisted commits as NLnet's policy on
generative AI asks, and the plan to implement it.

AI-assisted: Claude Code, model claude-opus-5-5
Prompts: asked for a provenance log according to NLnet's generative AI
  policy; first chose a redacted verbatim log in the repository, then
  rejected publishing raw conversations and asked how "or a summary
  thereof" can be met; decided on a summary block in each commit message,
  reviewed and approved by the person; asked how the block reaches main
  through pull requests and chose to prefer merge commits.
Output: the model drafted the specification and the implementation plan.
Human: Aarno set the scope, read the policy and the proposal form, chose
  the commit block over a published log, corrected the wording on the
  grant application and approved the specification.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

- [ ] **Step 3: After explicit approval, commit**

```bash
git add specs/provenance-log.md docs/superpowers/plans/2026-10-08-provenance-log.md
git commit -F <file holding the approved message>
```

---

### Task 1: Scaffolding and the commit message check

**Files:**
- Create: `pyproject.toml`, `noxfile.py`, `tools/check_commit_messages.py`
- Test: `tests/tools/test_check_commit_messages.py`

**Interfaces:**
- Produces: `is_ai_assisted(message: str) -> bool`, `missing_fields(message: str) -> list[str]`, `read_commits(revision_range: str) -> list[tuple[str, str]]`, `main(argv: list[str]) -> int`, constant `FIELDS`.
- Produces: `nox` sessions `tests`, `lint`, `commit_messages`; pytest finds modules in `tools/` through `pythonpath`.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "econoci"
version = "0.0.0"
description = "Find wasted CI runner time and say what to change."
readme = "README.md"
license = "Apache-2.0"
requires-python = ">=3.11"
dependencies = []

[tool.uv]
package = false

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["tools"]

[tool.ruff]
target-version = "py311"
# Code blocks in Markdown are illustrations, not code to reformat.
extend-exclude = ["*.md"]

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]
```

- [ ] **Step 2: Write `noxfile.py`**

```python
import nox

nox.options.default_venv_backend = "uv"
nox.options.sessions = ["lint", "tests", "commit_messages"]

# The initial commit predates specs/provenance-log.md.
FIRST_CHECKED_RANGE = "8076110..HEAD"


@nox.session(python="3.14")
def tests(session):
    session.install("pytest")
    session.run("pytest", *session.posargs)


@nox.session(python="3.14")
def lint(session):
    session.install("ruff")
    session.run("ruff", "check", ".")
    session.run("ruff", "format", "--check", ".")


@nox.session(python="3.14")
def commit_messages(session):
    session.run("python", "tools/check_commit_messages.py", FIRST_CHECKED_RANGE)
```

- [ ] **Step 3: Write the failing tests**

`tests/tools/test_check_commit_messages.py`:

```python
import os
import subprocess

import check_commit_messages as check
import pytest

TRAILER = "Co-Authored-By: Model X 1 <noreply@anthropic.com>"

COMPLETE = f"""Add a thing

Why the thing exists.

AI-assisted: Claude Code, model model-x-1
Prompts: asked for a thing;
  then asked for it to be smaller.
Output: the model drafted the thing.
Human: the person chose the size.

{TRAILER}
"""


def without(field):
    lines = COMPLETE.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f"{field}:"))
    end = start + 1
    while lines[end].startswith("  "):
        end += 1
    return "\n".join(lines[:start] + lines[end:]) + "\n"


def test_complete_block_passes():
    assert check.missing_fields(COMPLETE) == []


def test_multi_line_field_is_accepted():
    message = COMPLETE.replace(
        "Output: the model drafted the thing.",
        "Output:\n  the model drafted the thing\n  and its tests.",
    )
    assert check.missing_fields(message) == []


def test_no_block_reports_every_field():
    message = f"Add a thing\n\n{TRAILER}\n"
    assert check.missing_fields(message) == list(check.FIELDS)


@pytest.mark.parametrize("field", check.FIELDS)
def test_missing_field_is_named(field):
    assert check.missing_fields(without(field)) == [field]


def test_field_with_no_text_counts_as_missing():
    message = COMPLETE.replace("Human: the person chose the size.", "Human:")
    assert check.missing_fields(message) == ["Human"]


def test_commit_without_ai_trailer_needs_no_block():
    assert check.missing_fields("Fix a typo\n") == []


def test_human_co_author_is_not_ai():
    message = "Fix a typo\n\nCo-Authored-By: Pat Example <pat@example.org>\n"
    assert not check.is_ai_assisted(message)
    assert check.missing_fields(message) == []


def test_trailer_is_matched_in_any_case():
    message = "Add a thing\n\nco-authored-by: Model X <noreply@anthropic.com>\n"
    assert check.is_ai_assisted(message)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.org",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.org",
    }

    def commit(message):
        subprocess.run(
            [
                "git",
                "-c",
                "commit.gpgsign=false",
                "commit",
                "--allow-empty",
                "-m",
                message,
            ],
            cwd=tmp_path,
            env=env,
            check=True,
            capture_output=True,
        )

    subprocess.run(
        ["git", "init", "-b", "main"], cwd=tmp_path, check=True, capture_output=True
    )
    commit("Initial commit")
    monkeypatch.chdir(tmp_path)
    return commit


def test_range_with_complete_commits_passes(repo, capsys):
    repo(COMPLETE)
    repo("Fix a typo")
    assert check.main(["HEAD~2..HEAD"]) == 0
    assert "2 commits checked, 0 failed" in capsys.readouterr().out


def test_range_names_the_commit_and_the_field(repo, capsys):
    repo(without("Prompts"))
    assert check.main(["HEAD~1..HEAD"]) == 1
    out = capsys.readouterr().out
    assert "Add a thing: missing Prompts" in out
    assert "1 commits checked, 1 failed" in out


def test_empty_range_passes(repo, capsys):
    assert check.main(["HEAD..HEAD"]) == 0
    assert "0 commits checked, 0 failed" in capsys.readouterr().out


def test_bad_range_is_an_error_without_traceback(repo, capsys):
    assert check.main(["no-such-revision..HEAD"]) == 2
    assert "git log failed" in capsys.readouterr().err


def test_usage_error_without_a_range(capsys):
    assert check.main([]) == 2
    assert "usage" in capsys.readouterr().err
```

- [ ] **Step 4: Run the tests and watch them fail**

Run: `uvx nox -s tests`
Expected: collection error, `ModuleNotFoundError: No module named 'check_commit_messages'`

- [ ] **Step 5: Write `tools/check_commit_messages.py`**

```python
"""Check that AI-assisted commits describe their provenance.

usage: check_commit_messages.py <revision range>

See specs/provenance-log.md.
"""

import re
import subprocess
import sys

FIELDS = ("AI-assisted", "Prompts", "Output", "Human")
AI_MARKERS = ("claude", "anthropic", "copilot", "openai", "gpt", "gemini", "codex")
_TRAILER = re.compile(r"^co-authored-by:(.*)$", re.IGNORECASE | re.MULTILINE)


class GitError(Exception):
    pass


def is_ai_assisted(message: str) -> bool:
    return any(
        marker in value.lower()
        for value in _TRAILER.findall(message)
        for marker in AI_MARKERS
    )


def missing_fields(message: str) -> list[str]:
    """Return the block fields an AI-assisted message lacks, in block order."""
    if not is_ai_assisted(message):
        return []
    return [
        field
        for field in FIELDS
        if not re.search(
            rf"^{re.escape(field)}:[ \t]*(\S|\n[ \t]+\S)", message, re.MULTILINE
        )
    ]


def read_commits(revision_range: str) -> list[tuple[str, str]]:
    """Return (hash, message) for each commit in the range, newest first."""
    result = subprocess.run(
        ["git", "log", "--format=%H%x00%B%x00", "--end-of-options", revision_range],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise GitError(f"git log failed: {result.stderr.strip()}")
    parts = result.stdout.split("\x00")
    return [(parts[i].strip(), parts[i + 1]) for i in range(0, len(parts) - 1, 2)]


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: check_commit_messages.py <revision range>", file=sys.stderr)
        return 2
    try:
        commits = read_commits(argv[0])
    except GitError as error:
        print(error, file=sys.stderr)
        return 2
    failed = 0
    for commit, message in commits:
        missing = missing_fields(message)
        if missing:
            failed += 1
            subject = (message.strip().splitlines() or [""])[0]
            print(f"{commit[:10]} {subject}: missing {', '.join(missing)}")
    print(f"{len(commits)} commits checked, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 6: Run tests, lint and the check**

Run: `uvx nox`
Expected: `tests`, `lint` and `commit_messages` all succeed. `commit_messages` prints `1 commits checked, 0 failed` (the Task 0 commit). If `ruff format --check` fails, run `uvx ruff format .` and rerun.

- [ ] **Step 7: Draft the commit message, show it, commit after approval**

Draft:

```text
Add the commit message check and project scaffolding

tools/check_commit_messages.py fails when a commit has an AI co-author
trailer and lacks the AI-assisted block or one of its fields. nox runs
tests, lint and the check over every commit after the initial one.

AI-assisted: Claude Code, model claude-opus-5-5
Prompts: approved the specification and asked to continue with its
  implementation.
Output: the model wrote pyproject.toml, noxfile.py, the check and its
  tests.
Human: Aarno reviewed the plan and the result.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

```bash
git add pyproject.toml noxfile.py tools/check_commit_messages.py tests/tools/test_check_commit_messages.py
git commit -F <file holding the approved message>
```

---

### Task 2: The helper that prints prompts since the last commit

**Files:**
- Create: `tools/prompts_since_commit.py`
- Test: `tests/tools/test_prompts_since_commit.py`

**Interfaces:**
- Consumes: pytest `pythonpath = ["tools"]` and the `tests` session from Task 1.
- Produces: `Entry(timestamp, session, kind, text, model)`, `TranscriptError`, `read_records(path) -> list[dict]`, `session_entries(path) -> list[Entry]`, `collect(directory, since) -> list[Entry]`, `render(entries, since) -> str`, `parse_since(text) -> datetime`, `default_transcripts(repo, environ) -> Path`, `main(argv) -> int`.

Facts about the transcript format, observed on Claude Code 2.1.293:

- One JSON object per line in `~/.claude/projects/<slug>/<session id>.jsonl`. The slug is the repository path with every character outside `A-Za-z0-9` replaced by `-`.
- A typed prompt is a `user` record whose `message.content` is a string, or a list with `text` blocks. Injected text has `isMeta: true` or starts with a harness tag such as `<system-reminder>`.
- A slash command is a `user` record whose text starts with `<command-name>/name</command-name>` and carries `<command-args>`.
- An answer to a question is a `user` record with a `tool_result` block whose `tool_use_id` matches an `AskUserQuestion` `tool_use` block of an earlier `assistant` record. The record's `toolUseResult.answers` maps each question to its answer.
- The model id is `message.model` on `assistant` records.
- A prompt typed while the assistant is working can arrive as an `attachment` record with `attachment.type == "queued_command"` and the text in `attachment.prompt`. This shape was not present in the local transcripts and comes from knowledge of Claude Code, so the code fails loudly if the attachment has no usable `prompt`.

- [ ] **Step 1: Write the failing tests**

`tests/tools/test_prompts_since_commit.py`:

```python
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import prompts_since_commit as psc
import pytest

SINCE = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)
BEFORE = "2026-01-02T11:59:59.000Z"
T1 = "2026-01-02T12:00:01.000Z"
T2 = "2026-01-02T12:00:02.000Z"
T3 = "2026-01-02T12:00:03.000Z"
T4 = "2026-01-02T12:00:04.000Z"


def user(stamp, content, **extra):
    return {
        "type": "user",
        "timestamp": stamp,
        "message": {"role": "user", "content": content},
        **extra,
    }


def assistant(stamp, content, model="model-x-1"):
    return {
        "type": "assistant",
        "timestamp": stamp,
        "message": {"role": "assistant", "model": model, "content": content},
    }


def reply(stamp, text="Done.", model="model-x-1"):
    return assistant(stamp, [{"type": "text", "text": text}], model)


def write(directory, name, records, tail=""):
    path = directory / f"{name}.jsonl"
    body = "".join(json.dumps(record) + "\n" for record in records)
    path.write_text(body + tail, encoding="utf-8")
    return path


def texts(entries):
    return [(entry.kind, entry.text) for entry in entries]


def test_prompts_after_the_cutoff_in_order(tmp_path):
    write(
        tmp_path,
        "aaaaaaaa-1",
        [
            user(BEFORE, "too early"),
            user(T1, "add a rule"),
            reply(T2),
            user(T3, [{"type": "text", "text": "make it smaller"}]),
        ],
    )
    assert texts(psc.collect(tmp_path, SINCE)) == [
        ("prompt", "add a rule"),
        ("prompt", "make it smaller"),
    ]


def test_sessions_are_merged_in_time_order(tmp_path):
    write(tmp_path, "aaaaaaaa-1", [user(T1, "first"), user(T3, "third")])
    write(tmp_path, "bbbbbbbb-2", [user(T2, "second"), user(T4, "fourth")])
    entries = psc.collect(tmp_path, SINCE)
    assert [entry.text for entry in entries] == ["first", "second", "third", "fourth"]
    assert [entry.session for entry in entries] == [
        "aaaaaaaa",
        "bbbbbbbb",
        "aaaaaaaa",
        "bbbbbbbb",
    ]


def question(stamp, tool_id):
    return assistant(
        stamp,
        [{"type": "tool_use", "id": tool_id, "name": "AskUserQuestion", "input": {}}],
    )


def test_answer_to_a_question_is_printed(tmp_path):
    write(
        tmp_path,
        "aaaaaaaa-1",
        [
            question(T1, "q1"),
            user(
                T2,
                [{"type": "tool_result", "tool_use_id": "q1", "content": "raw"}],
                toolUseResult={"answers": {"Which size?": "Small"}},
            ),
        ],
    )
    assert texts(psc.collect(tmp_path, SINCE)) == [("answer", "Which size? -> Small")]


def test_answer_falls_back_to_the_result_text(tmp_path):
    write(
        tmp_path,
        "aaaaaaaa-1",
        [
            question(T1, "q1"),
            user(
                T2,
                [
                    {
                        "type": "tool_result",
                        "tool_use_id": "q1",
                        "content": [{"type": "text", "text": "The person declined."}],
                    }
                ],
            ),
        ],
    )
    assert texts(psc.collect(tmp_path, SINCE)) == [("answer", "The person declined.")]


def test_injected_text_tool_output_and_replies_are_left_out(tmp_path):
    write(
        tmp_path,
        "aaaaaaaa-1",
        [
            user(T1, "the body of a skill", isMeta=True),
            user(T1, "a summary of the session so far", isCompactSummary=True),
            user(T1, "<system-reminder>be careful</system-reminder>"),
            user(T1, "<local-command-stdout>ok</local-command-stdout>"),
            assistant(
                T2, [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {}}]
            ),
            user(
                T2, [{"type": "tool_result", "tool_use_id": "t1", "content": "files"}]
            ),
            reply(T3, "Here is what I found."),
            user(T4, "a subagent prompt", isSidechain=True),
            {"type": "system", "timestamp": T4, "content": "turn ended"},
        ],
    )
    assert psc.collect(tmp_path, SINCE) == []


def test_slash_command_is_shown_as_typed(tmp_path):
    command = (
        "<command-name>/review</command-name>\n"
        "<command-message>review</command-message>\n"
        "<command-args>high</command-args>"
    )
    write(tmp_path, "aaaaaaaa-1", [user(T1, command)])
    assert texts(psc.collect(tmp_path, SINCE)) == [("prompt", "/review high")]


def test_queued_prompt_is_printed(tmp_path):
    queued = {
        "type": "attachment",
        "timestamp": T1,
        "attachment": {"type": "queued_command", "prompt": "also add a test"},
    }
    other = {"type": "attachment", "timestamp": T1, "attachment": {"type": "date"}}
    write(tmp_path, "aaaaaaaa-1", [queued, other])
    assert texts(psc.collect(tmp_path, SINCE)) == [("prompt", "also add a test")]


def test_queued_prompt_without_text_is_an_error(tmp_path):
    queued = {
        "type": "attachment",
        "timestamp": T1,
        "attachment": {"type": "queued_command"},
    }
    write(tmp_path, "aaaaaaaa-1", [queued])
    with pytest.raises(psc.TranscriptError, match="queued_command"):
        psc.collect(tmp_path, SINCE)


def test_model_comes_from_the_reply_that_follows(tmp_path):
    write(
        tmp_path,
        "aaaaaaaa-1",
        [
            user(T1, "first"),
            reply(T2, model="model-x-1"),
            user(T3, "second"),
            reply(T4, model="model-y-2"),
            user(T4, "third"),
        ],
    )
    entries = psc.collect(tmp_path, SINCE)
    assert [entry.model for entry in entries] == ["model-x-1", "model-y-2", "model-y-2"]


def test_model_is_unknown_without_any_reply(tmp_path):
    write(tmp_path, "aaaaaaaa-1", [user(T1, "first"), reply(T2, model="<synthetic>")])
    assert [entry.model for entry in psc.collect(tmp_path, SINCE)] == ["unknown"]


def test_unknown_record_type_is_an_error_that_names_it(tmp_path):
    write(tmp_path, "aaaaaaaa-1", [user(T1, "first"), {"type": "brand-new"}])
    with pytest.raises(psc.TranscriptError, match="aaaaaaaa-1.jsonl:2.*'brand-new'"):
        psc.collect(tmp_path, SINCE)


def test_unfinished_last_line_is_skipped(tmp_path):
    write(tmp_path, "aaaaaaaa-1", [user(T1, "first")], tail='{"type": "us')
    assert texts(psc.collect(tmp_path, SINCE)) == [("prompt", "first")]


def test_broken_line_before_the_end_is_an_error(tmp_path):
    path = write(tmp_path, "aaaaaaaa-1", [user(T1, "first")])
    path.write_text("{broken\n" + path.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(psc.TranscriptError, match="aaaaaaaa-1.jsonl:1: not JSON"):
        psc.collect(tmp_path, SINCE)


def test_prompt_without_timestamp_is_an_error(tmp_path):
    record = user(T1, "first")
    del record["timestamp"]
    write(tmp_path, "aaaaaaaa-1", [record])
    with pytest.raises(psc.TranscriptError, match="without a timestamp"):
        psc.collect(tmp_path, SINCE)


def test_session_file_older_than_the_cutoff_is_not_read(tmp_path):
    stale = write(tmp_path, "aaaaaaaa-1", [{"type": "from-an-old-version"}])
    old = SINCE.timestamp() - 3600
    os.utime(stale, (old, old))
    write(tmp_path, "bbbbbbbb-2", [user(T1, "first")])
    assert texts(psc.collect(tmp_path, SINCE)) == [("prompt", "first")]


def test_render_lists_models_and_indents_text(tmp_path):
    write(tmp_path, "aaaaaaaa-1", [user(T1, "add a rule\nwith two lines"), reply(T2)])
    out = psc.render(psc.collect(tmp_path, SINCE), SINCE)
    assert out.splitlines() == [
        "Prompts since 2026-01-02T12:00:00+00:00",
        "Models: model-x-1",
        "",
        "2026-01-02T12:00:01Z  aaaaaaaa  prompt  model-x-1",
        "    add a rule",
        "    with two lines",
    ]


def test_render_says_when_there_is_nothing():
    assert psc.render([], SINCE) == "No prompts since 2026-01-02T12:00:00+00:00.\n"


def test_since_needs_a_utc_offset():
    assert psc.parse_since("2026-01-02T12:00:00Z") == SINCE
    assert psc.parse_since("2026-01-02T13:00:00+01:00") == SINCE
    with pytest.raises(psc.TranscriptError, match="UTC offset"):
        psc.parse_since("2026-01-02T12:00:00")
    with pytest.raises(psc.TranscriptError, match="not a timestamp"):
        psc.parse_since("yesterday")


def test_default_transcripts_directory():
    repo = Path("/home/pat/dev/my.project")
    assert psc.default_transcripts(repo, {"CLAUDE_CONFIG_DIR": "/cfg"}) == Path(
        "/cfg/projects/-home-pat-dev-my-project"
    )
    assert psc.default_transcripts(repo, {}) == (
        Path.home() / ".claude/projects/-home-pat-dev-my-project"
    )


def test_main_prints_prompts(tmp_path, capsys):
    write(tmp_path, "aaaaaaaa-1", [user(T1, "add a rule"), reply(T2)])
    code = psc.main(["--since", "2026-01-02T12:00:00Z", "--transcripts", str(tmp_path)])
    assert code == 0
    assert "    add a rule" in capsys.readouterr().out


def test_main_reports_a_missing_directory(tmp_path, capsys):
    missing = tmp_path / "nowhere"
    code = psc.main(["--since", "2026-01-02T12:00:00Z", "--transcripts", str(missing)])
    assert code == 1
    assert f"no transcript directory at {missing}" in capsys.readouterr().err


def test_main_reports_a_transcript_error(tmp_path, capsys):
    write(tmp_path, "aaaaaaaa-1", [{"type": "brand-new"}])
    code = psc.main(["--since", "2026-01-02T12:00:00Z", "--transcripts", str(tmp_path)])
    assert code == 1
    assert "unknown record type 'brand-new'" in capsys.readouterr().err
```

- [ ] **Step 2: Run the tests and watch them fail**

Run: `uvx nox -s tests -- tests/tools/test_prompts_since_commit.py`
Expected: collection error, `ModuleNotFoundError: No module named 'prompts_since_commit'`

- [ ] **Step 3: Write `tools/prompts_since_commit.py`**

```python
"""Print what the person asked Claude Code since the last commit.

The output is the raw material for the Prompts field of the AI-assisted block
in a commit message. It goes to the terminal only. See specs/provenance-log.md.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

# Record types seen in Claude Code 2.1.293. The format is internal to Claude
# Code, so an unknown type stops the run instead of being skipped.
KNOWN_TYPES = frozenset(
    {
        "ai-title",
        "assistant",
        "atis-latch",
        "attachment",
        "bridge-session",
        "cost-state",
        "file-history-delta",
        "file-history-snapshot",
        "last-prompt",
        "mode",
        "permission-mode",
        "queue-operation",
        "system",
        "user",
    }
)
HARNESS_PREFIXES = (
    "<bash-input>",
    "<bash-stderr>",
    "<bash-stdout>",
    "<local-command-caveat>",
    "<local-command-stderr>",
    "<local-command-stdout>",
    "<system-reminder>",
    "<task-notification>",
    "<user-prompt-submit-hook>",
)
QUESTION_TOOL = "AskUserQuestion"
_COMMAND_NAME = re.compile(r"<command-name>(.*?)</command-name>", re.DOTALL)
_COMMAND_ARGS = re.compile(r"<command-args>(.*?)</command-args>", re.DOTALL)


class TranscriptError(Exception):
    pass


@dataclass
class Entry:
    timestamp: datetime
    session: str
    kind: str  # "prompt" or "answer"
    text: str
    model: str = "unknown"


def read_records(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").split("\n")
    records = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            if number == len(lines):
                break  # the session is still writing its last line
            raise TranscriptError(
                f"{path.name}:{number}: not JSON ({error.msg})"
            ) from error
        kind = record.get("type") if isinstance(record, dict) else None
        if kind not in KNOWN_TYPES:
            raise TranscriptError(f"{path.name}:{number}: unknown record type {kind!r}")
        records.append(record)
    return records


def prompt_text(raw: str) -> str | None:
    """Return what the person typed, or None for text the harness injected."""
    text = raw.strip()
    if text.startswith("<command-"):
        name = _COMMAND_NAME.search(text)
        if name is None:
            return None
        arguments = _COMMAND_ARGS.search(text)
        return f"{name[1]} {arguments[1] if arguments else ''}".strip()
    if not text or text.startswith(HARNESS_PREFIXES):
        return None
    return text


def answer_text(record: dict, block: dict) -> str:
    result = record.get("toolUseResult")
    if isinstance(result, dict) and isinstance(result.get("answers"), dict):
        return "\n".join(f"{q} -> {a}" for q, a in result["answers"].items())
    content = block.get("content")
    if isinstance(content, list):
        content = "\n".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    return str(content or "").strip()


def queued_text(path: Path, attachment: dict) -> str:
    prompt = attachment.get("prompt")
    if isinstance(prompt, list):
        prompt = "\n".join(
            part.get("text", "") for part in prompt if isinstance(part, dict)
        )
    if not isinstance(prompt, str) or not prompt.strip():
        raise TranscriptError(f"{path.name}: queued_command attachment without text")
    return prompt.strip()


def session_entries(path: Path) -> list[Entry]:
    entries: list[Entry] = []
    waiting: list[Entry] = []  # entries whose reply, and so model, is still to come
    question_ids: set[str] = set()
    last_model = "unknown"
    session = path.stem[:8]

    def add(record: dict, kind: str, text: str) -> None:
        stamp = record.get("timestamp")
        if not stamp:
            raise TranscriptError(
                f"{path.name}: {record['type']} record without a timestamp"
            )
        entry = Entry(datetime.fromisoformat(stamp), session, kind, text)
        entries.append(entry)
        waiting.append(entry)

    for record in read_records(path):
        if record.get("isSidechain"):
            continue
        kind = record["type"]
        if kind == "assistant":
            message = record.get("message") or {}
            model = message.get("model")
            if model and model != "<synthetic>":
                last_model = model
                for entry in waiting:
                    entry.model = model
                waiting.clear()
            for block in message.get("content") or []:
                if (
                    isinstance(block, dict)
                    and block.get("type") == "tool_use"
                    and block.get("name") == QUESTION_TOOL
                ):
                    question_ids.add(block["id"])
        elif kind == "user":
            if record.get("isMeta") or record.get("isCompactSummary"):
                continue
            content = (record.get("message") or {}).get("content")
            if isinstance(content, str):
                content = [{"type": "text", "text": content}]
            for block in content or []:
                if block.get("type") == "text":
                    text = prompt_text(block.get("text", ""))
                    if text:
                        add(record, "prompt", text)
                elif (
                    block.get("type") == "tool_result"
                    and block.get("tool_use_id") in question_ids
                ):
                    add(record, "answer", answer_text(record, block))
        elif kind == "attachment":
            attachment = record.get("attachment") or {}
            if attachment.get("type") == "queued_command":
                add(record, "prompt", queued_text(path, attachment))
    for entry in waiting:
        entry.model = last_model
    return entries


def collect(directory: Path, since: datetime) -> list[Entry]:
    """Return the entries of every session in the directory from `since` onward."""
    entries: list[Entry] = []
    for path in sorted(directory.glob("*.jsonl")):
        if path.stat().st_mtime < since.timestamp():
            continue  # last written before the cut-off, so nothing in it counts
        entries += [e for e in session_entries(path) if e.timestamp >= since]
    return sorted(entries, key=lambda entry: (entry.timestamp, entry.session))


def render(entries: list[Entry], since: datetime) -> str:
    if not entries:
        return f"No prompts since {since.isoformat()}.\n"
    models = sorted({entry.model for entry in entries})
    lines = [f"Prompts since {since.isoformat()}", f"Models: {', '.join(models)}"]
    for entry in entries:
        stamp = entry.timestamp.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        lines.append("")
        lines.append(f"{stamp}  {entry.session}  {entry.kind}  {entry.model}")
        lines += [f"    {line}" for line in entry.text.splitlines()]
    return "\n".join(lines) + "\n"


def parse_since(text: str) -> datetime:
    try:
        since = datetime.fromisoformat(text)
    except ValueError as error:
        raise TranscriptError(f"--since {text!r} is not a timestamp") from error
    if since.tzinfo is None:
        raise TranscriptError(f"--since {text!r} needs a UTC offset, for example Z")
    return since


def default_transcripts(repo: Path, environ: Mapping[str, str]) -> Path:
    base = Path(environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    return base / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(repo))


def git(*arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise TranscriptError(f"git {arguments[0]} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--since",
        help="timestamp with UTC offset (default: committer date of HEAD)",
    )
    parser.add_argument(
        "--transcripts",
        type=Path,
        help="directory with Claude Code session files (default: this repository's)",
    )
    args = parser.parse_args(argv)
    try:
        since = parse_since(args.since or git("log", "-1", "--format=%cI"))
        directory = args.transcripts or default_transcripts(
            Path(git("rev-parse", "--show-toplevel")), os.environ
        )
        if not directory.is_dir():
            raise TranscriptError(f"no transcript directory at {directory}")
        sys.stdout.write(render(collect(directory, since), since))
    except TranscriptError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run tests and lint**

Run: `uvx nox -s tests lint`
Expected: all pass. If `ruff format --check` fails, run `uvx ruff format .` and rerun.

- [ ] **Step 5: Run the helper on the real transcripts**

Run: `python3 tools/prompts_since_commit.py`
Expected: exit code 0 and the prompts typed since the Task 1 commit. An "unknown record type" error means the format moved since 2.1.293: stop and report the type instead of adding it blindly.

Then run: `python3 tools/prompts_since_commit.py --since 2026-10-08T07:11:57Z`
Expected: the whole session, starting with the request for a provenance log, including the three multiple-choice answers.

- [ ] **Step 6: Draft the commit message from the helper's output, show it, commit after approval**

Draft, with `Prompts` rewritten from Step 5's first run:

```text
Add the helper that lists prompts since the last commit

tools/prompts_since_commit.py reads Claude Code's local session files
and prints what the person typed or answered since HEAD was committed.
The Prompts field of the AI-assisted block is drafted from its output.

AI-assisted: Claude Code, model claude-opus-5-5
Prompts: <summary of the helper's output>
Output: the model wrote the helper and its tests.
Human: Aarno reviewed the result.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

```bash
git add tools/prompts_since_commit.py tests/tools/test_prompts_since_commit.py
git commit -F <file holding the approved message>
```

---

### Task 3: The rule in README.md and CLAUDE.md

**Files:**
- Modify: `README.md` (section "Use of generative AI")
- Modify: `CLAUDE.md` (sections "Working rules" and "Layout")

**Interfaces:**
- Consumes: `tools/prompts_since_commit.py` and the `commit_messages` session by name.

- [ ] **Step 1: Update `README.md`**

Replace:

```markdown
AI-assisted commits carry a `Co-Authored-By:` line naming the model.
econoCI itself uses no language model at run time.
```

with:

```markdown
AI-assisted commits carry a `Co-Authored-By:` line. Their message names the
model, summarizes the prompts that led to the commit, and says what the model
produced and what the person decided or checked. `specs/provenance-log.md`
describes the format. econoCI itself uses no language model at run time.
```

- [ ] **Step 2: Update `CLAUDE.md`**

Replace:

```markdown
- **Mark AI-assisted commits** with the co-author line.
```

with:

```markdown
- **Mark AI-assisted commits** with the co-author line and the `AI-assisted`
  block from `specs/provenance-log.md`. Run
  `python3 tools/prompts_since_commit.py` and read `git diff --cached`. Draft
  `Prompts` from the first and `Output` from the second. Show the full commit
  message with `git diff --cached --stat`, name every change no prompt asked
  for and every prompt that left no trace in the diff, and commit only after
  explicit approval, with the message exactly as approved.
- **Merge with a merge commit.** A squash is allowed only when its message
  carries the blocks of the squashed commits, merged into one.
```

Replace:

```markdown
The product goes under `src/econoci/` as the design describes.
```

with:

```markdown
The product goes under `src/econoci/` as the design describes. Project tooling
that is not part of the product goes under `tools/`.
```

- [ ] **Step 3: Run everything**

Run: `uvx nox`
Expected: all sessions pass. `commit_messages` prints `3 commits checked, 0 failed`.

- [ ] **Step 4: Draft the commit message from the helper's output, show it, commit after approval**

Run: `python3 tools/prompts_since_commit.py`

Draft, with `Prompts` rewritten from that output:

```text
Describe the AI-assisted commit block in README and CLAUDE.md

AI-assisted: Claude Code, model claude-opus-5-5
Prompts: <summary of the helper's output>
Output: the model wrote the README sentence and the two working rules.
Human: Aarno reviewed the wording.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

```bash
git add README.md CLAUDE.md
git commit -F <file holding the approved message>
```

- [ ] **Step 5: Final check**

Run: `uvx nox -s commit_messages`
Expected: `4 commits checked, 0 failed`.

Merging `provenance-commit-block` into `main` is Aarno's decision. Per the spec it is a merge commit: `git switch main && git merge --no-ff provenance-commit-block`.
