"""Check that AI-assisted commits reached main through a person's review.

usage: check_review_trailers.py <revision range>

A merge commit made by a person is the record of their review of what it
brings in. Every AI-assisted commit on the first-parent line, merge commits
included, needs a Reviewed-by trailer of its own. See
specs/provenance-log.md, "From a branch to main".
"""

import re
import subprocess
import sys

from check_commit_messages import AI_MARKERS, GitError, is_ai_assisted

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
        if is_reviewed(message) or not is_ai_assisted(message):
            continue
        subject = (message.strip().splitlines() or [""])[0]
        if len(parents) > 1:
            # A merge commit can carry changes of its own.
            reason = "AI-assisted merge commit"
        else:
            reason = "AI-assisted commit outside a merge"
        failures.append((commit, subject, reason))
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
    print(f"{checked} commits on the first-parent line checked, {len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
