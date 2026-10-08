# Review Trailer Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `nox` fails when an AI-assisted commit has reached `main` without a `Reviewed-by:` trailer on the merge commit that brought it in, or on the commit itself.

**Architecture:** One new script, `tools/check_review_trailers.py`, walks the first-parent history of a revision range. It reuses `is_ai_assisted` and `read_commits` from `tools/check_commit_messages.py`. A `nox` session runs it over `8076110..main`.

**Tech Stack:** Python standard library, `pytest`, `ruff`, `nox`, run through `uvx nox`. Tested on Python 3.14.

**Spec:** `specs/provenance-log.md`, sections "Checks", "From a branch to main" and "Tests" (review check).

## Global Constraints

- Standard library only in `tools/`. No network calls, no language model.
- Test data is synthetic: histories are built in a temporary git repository, with invented names.
- Write the failing test first and watch it fail.
- The rule, copied from the spec: on the first-parent history of `main`, a merge commit that brings in at least one AI-assisted commit has a `Reviewed-by:` trailer, and an AI-assisted commit that is not brought in by a merge commit has one itself. A trailer that names an AI model does not count.
- The session checks `8076110..main`, never `HEAD`: commits on a branch are not reviewed yet.
- This work is part of the implementation commit of the provenance tooling, not a commit of its own. One commit per unit of requested work.
- Prose rules: no em dashes, American English.

## Review Focus

1. **A fast-forward merge.** It creates no merge commit, so the branch's AI-assisted commits sit on the first-parent line and each fails. The message says the commit is outside a merge, which tells the person what to redo. (Task 1)
2. **No local `main` ref**, as in a CI checkout of a pull request. One-line git error and exit code 2, no traceback. (Task 1)
3. **`reviewed-by:` in lower case or with trailing spaces.** Accepted. (Task 1)
4. **A trailer with no name.** `Reviewed-by:` followed by nothing does not count. (Task 1)
5. **A merge of `main` into a feature branch that is later merged.** Only the first-parent line of `main` is walked, so the back-merge is not itself required to carry a trailer. (Task 1)

## File Structure

| File | Responsibility |
| --- | --- |
| `tools/check_review_trailers.py` | Decide whether a message records a review; find first-parent commits that need one and lack it. |
| `tests/tools/test_check_review_trailers.py` | Tests, each on a small git history. |
| `noxfile.py` | New session `review_trailers`, added to the default sessions. |

---

### Task 1: The review trailer check

**Files:**
- Create: `tools/check_review_trailers.py`
- Test: `tests/tools/test_check_review_trailers.py`
- Modify: `noxfile.py`

**Interfaces:**
- Consumes from `tools/check_commit_messages.py`: `AI_MARKERS: tuple[str, ...]`, `GitError`, `is_ai_assisted(message: str) -> bool`, `read_commits(revision_range: str) -> list[tuple[str, str]]`.
- Produces: `is_reviewed(message: str) -> bool`, `first_parent_commits(revision_range: str) -> list[tuple[str, list[str], str]]`, `unreviewed(revision_range: str) -> tuple[int, list[tuple[str, str, str]]]`, `main(argv: list[str]) -> int`.

- [ ] **Step 1: Write the failing tests**

`tests/tools/test_check_review_trailers.py`:

```python
import os
import subprocess

import check_review_trailers as review
import pytest

AI = "Co-Authored-By: Model X 1 <noreply@anthropic.com>"
REVIEWED = "Reviewed-by: Pat Example <pat@example.org>"
AI_COMMIT = f"Add a thing\n\n{AI}\n"


@pytest.fixture
def git(tmp_path, monkeypatch):
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.org",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.org",
    }

    def run(*arguments):
        subprocess.run(
            ["git", "-c", "commit.gpgsign=false", *arguments],
            cwd=tmp_path,
            env=env,
            check=True,
            capture_output=True,
        )

    run("init", "-b", "main")
    run("commit", "--allow-empty", "-m", "Initial commit")
    run("tag", "base")
    monkeypatch.chdir(tmp_path)
    return run


def commit(git, message):
    git("commit", "--allow-empty", "-m", message)


def branch(git, name, *messages):
    git("switch", "-c", name)
    for message in messages:
        commit(git, message)
    git("switch", "main")


def merge(git, name, message):
    git("merge", "--no-ff", "-m", message, name)


def test_reviewed_by_trailer_is_recognized():
    assert review.is_reviewed(f"Merge work\n\n{REVIEWED}\n")
    assert review.is_reviewed("Merge work\n\nreviewed-by: Pat Example  \n")


def test_trailer_without_a_name_does_not_count():
    assert not review.is_reviewed("Merge work\n\nReviewed-by:\n")
    assert not review.is_reviewed("Merge work\n\nReviewed-by:   \n")


def test_trailer_naming_an_ai_model_does_not_count():
    assert not review.is_reviewed("Merge work\n\nReviewed-by: Model X <noreply@anthropic.com>\n")


def test_reviewed_merge_of_ai_commits_passes(git, capsys):
    branch(git, "work", AI_COMMIT, "Fix a typo")
    merge(git, "work", f"Merge work\n\n{REVIEWED}")
    assert review.main(["base..main"]) == 0
    out = capsys.readouterr().out
    assert "1 commits on the first-parent line checked, 0 failed" in out


def test_merge_of_ai_commits_without_trailer_fails_and_is_named(git, capsys):
    branch(git, "work", AI_COMMIT, AI_COMMIT)
    merge(git, "work", "Merge work")
    assert review.main(["base..main"]) == 1
    out = capsys.readouterr().out
    assert "Merge work: brings in 2 AI-assisted commits, no Reviewed-by" in out
    assert "1 commits on the first-parent line checked, 1 failed" in out


def test_merge_reviewed_by_an_ai_model_fails(git, capsys):
    branch(git, "work", AI_COMMIT)
    merge(git, "work", "Merge work\n\nReviewed-by: Model X <noreply@anthropic.com>")
    assert review.main(["base..main"]) == 1


def test_merge_without_ai_commits_needs_no_trailer(git, capsys):
    branch(git, "work", "Fix a typo")
    merge(git, "work", "Merge work")
    assert review.main(["base..main"]) == 0


def test_ai_commit_outside_a_merge_fails_and_is_named(git, capsys):
    commit(git, AI_COMMIT)
    assert review.main(["base..main"]) == 1
    out = capsys.readouterr().out
    assert "Add a thing: AI-assisted commit outside a merge, no Reviewed-by" in out


def test_fast_forwarded_ai_commits_fail(git, capsys):
    branch(git, "work", AI_COMMIT)
    git("merge", "--ff-only", "work")
    assert review.main(["base..main"]) == 1
    assert "outside a merge" in capsys.readouterr().out


def test_ai_commit_outside_a_merge_passes_with_its_own_trailer(git):
    commit(git, f"Add a thing\n\n{REVIEWED}\n{AI}\n")
    assert review.main(["base..main"]) == 0


def test_human_commit_on_main_needs_no_trailer(git):
    commit(git, "Fix a typo")
    assert review.main(["base..main"]) == 0


def test_back_merge_inside_a_branch_needs_no_trailer(git):
    git("switch", "-c", "work")
    commit(git, AI_COMMIT)
    git("switch", "main")
    commit(git, "Fix a typo")
    git("switch", "work")
    git("merge", "--no-ff", "-m", "Merge main into work", "main")
    git("switch", "main")
    merge(git, "work", f"Merge work\n\n{REVIEWED}")
    assert review.main(["base..main"]) == 0


def test_missing_ref_is_an_error_without_traceback(git, capsys):
    assert review.main(["base..no-such-branch"]) == 2
    assert "git log failed" in capsys.readouterr().err


def test_usage_error_without_a_range(capsys):
    assert review.main([]) == 2
    assert "usage" in capsys.readouterr().err
```

- [ ] **Step 2: Run the tests and watch them fail**

Run: `uvx nox -s tests -- tests/tools/test_check_review_trailers.py`
Expected: collection error, `ModuleNotFoundError: No module named 'check_review_trailers'`

- [ ] **Step 3: Write `tools/check_review_trailers.py`**

```python
"""Check that AI-assisted commits on main have a recorded review.

usage: check_review_trailers.py <revision range>

A merge commit that brings in AI-assisted commits needs a Reviewed-by trailer.
So does an AI-assisted commit that reached the first-parent line without a
merge commit. See specs/provenance-log.md, "From a branch to main".
"""

import re
import subprocess
import sys

from check_commit_messages import AI_MARKERS, GitError, is_ai_assisted, read_commits

_REVIEWED = re.compile(r"^reviewed-by:(.*)$", re.IGNORECASE | re.MULTILINE)


def is_reviewed(message: str) -> bool:
    """True when a Reviewed-by trailer names someone who is not an AI model."""
    return any(
        value.strip() and not any(marker in value.lower() for marker in AI_MARKERS)
        for value in _REVIEWED.findall(message)
    )


def first_parent_commits(revision_range: str) -> list[tuple[str, list[str], str]]:
    """Return (hash, parents, message) along the first-parent line, newest first."""
    result = subprocess.run(
        [
            "git",
            "log",
            "--first-parent",
            "--format=%H%x00%P%x00%B%x00",
            "--end-of-options",
            revision_range,
            "--",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise GitError(f"git log failed: {result.stderr.strip()}")
    parts = result.stdout.split("\x00")
    return [
        (parts[i].strip(), parts[i + 1].split(), parts[i + 2])
        for i in range(0, len(parts) - 2, 3)
    ]


def unreviewed(revision_range: str) -> tuple[int, list[tuple[str, str, str]]]:
    """Return the number of commits checked and (hash, subject, reason) per failure."""
    commits = first_parent_commits(revision_range)
    failures = []
    for commit, parents, message in commits:
        if is_reviewed(message):
            continue
        subject = (message.strip().splitlines() or [""])[0]
        if len(parents) > 1:
            brought_in = sum(
                is_ai_assisted(other_message)
                for other, other_message in read_commits(f"{commit}^1..{commit}")
                if other != commit
            )
            if brought_in:
                reason = f"brings in {brought_in} AI-assisted commits"
                failures.append((commit, subject, reason))
        elif is_ai_assisted(message):
            failures.append((commit, subject, "AI-assisted commit outside a merge"))
    return len(commits), failures


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: check_review_trailers.py <revision range>", file=sys.stderr)
        return 2
    try:
        checked, failures = unreviewed(argv[0])
    except GitError as error:
        print(error, file=sys.stderr)
        return 2
    for commit, subject, reason in failures:
        print(f"{commit[:10]} {subject}: {reason}, no Reviewed-by trailer")
    print(
        f"{checked} commits on the first-parent line checked, {len(failures)} failed"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run the tests**

Run: `uvx nox -s tests`
Expected: all pass, including the 71 existing tests.

- [ ] **Step 5: Add the `nox` session**

In `noxfile.py`, replace:

```python
nox.options.sessions = ["lint", "tests", "commit_messages"]
```

with:

```python
nox.options.sessions = ["lint", "tests", "commit_messages", "review_trailers"]
```

and append:

```python
@nox.session(python="3.14")
def review_trailers(session):
    # main, not HEAD: commits on a branch are not reviewed yet.
    session.run("python", "tools/check_review_trailers.py", "8076110..main")
```

- [ ] **Step 6: Run everything**

Run: `uvx nox`
Expected: `lint`, `tests`, `commit_messages` and `review_trailers` succeed. `review_trailers` prints `0 commits on the first-parent line checked, 0 failed`, because `main` is still at `8076110`. If `ruff format --check` fails, run `uvx ruff format .` and rerun.

- [ ] **Step 7: No commit of its own**

The files join the implementation commit of the provenance tooling. Its message is drafted and shown for approval as the spec describes.

## After the merge

Once Aarno has reviewed the branch and it is merged with a merge commit that carries `Reviewed-by:`, `uvx nox -s review_trailers` prints `1 commits on the first-parent line checked, 0 failed`. If the trailer was forgotten, the session fails and names the merge commit; amending the merge commit message before pushing fixes it.
