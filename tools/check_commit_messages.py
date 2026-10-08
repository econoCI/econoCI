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
        [
            "git",
            "log",
            "--format=%H%x00%B%x00",
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
