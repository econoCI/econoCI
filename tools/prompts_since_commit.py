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

# Record types seen in Claude Code up to 2.1.293. The format is internal to
# Claude Code, so an unknown type stops the run instead of being skipped.
KNOWN_TYPES = frozenset(
    {
        "agent-name",
        "ai-title",
        "artifact-autoreact-ledger",
        "artifact-comment-monitor",
        "assistant",
        "atis-latch",
        "attachment",
        "bridge-session",
        "continued-in",
        "cost-state",
        "custom-title",
        "file-history-delta",
        "file-history-snapshot",
        "frame-link",
        "last-prompt",
        "mode",
        "permission-mode",
        "pr-link",
        "queue-operation",
        "relocated",
        "system",
        "user",
        "worktree-state",
    }
)
HARNESS_PREFIXES = (
    "[Request interrupted by user",
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
    kind: str  # "prompt", "answer" or "feedback"
    text: str
    model: str = "unknown"


def read_records(path: Path) -> list[dict]:
    # A last line cut inside a character must not stop the read: it turns into
    # a replacement character and is skipped below like any unfinished line.
    lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
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


def origin_kind(holder: dict) -> str | None:
    origin = holder.get("origin")
    return origin.get("kind") if isinstance(origin, dict) else origin


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
            if origin_kind(record) not in (None, "human"):
                continue  # a message from another agent, not from the person
            feedback = record.get("userFeedback")
            if isinstance(feedback, str) and feedback.strip():
                # typed when the person rejected a tool call or a plan
                add(record, "feedback", feedback.strip())
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
            # A queued command is a prompt typed while the assistant was busy,
            # but the same record type carries task notifications and messages
            # from other agents.
            if (
                attachment.get("type") == "queued_command"
                and attachment.get("commandMode") == "prompt"
                and origin_kind(attachment) == "human"
                and not attachment.get("isMeta")
            ):
                text = prompt_text(queued_text(path, attachment))
                if text:
                    add(record, "prompt", text)
    for entry in waiting:
        entry.model = last_model
    return entries


def live_sessions(directory: Path, since: datetime) -> list[Path]:
    """Return the session files written to since the cut-off.

    A file last written before it holds nothing that counts, and may be in a
    format this script no longer knows.
    """
    return [
        path
        for path in sorted(directory.glob("*.jsonl"))
        if path.stat().st_mtime >= since.timestamp()
    ]


def collect(directory: Path, since: datetime) -> list[Entry]:
    """Return the entries of every session in the directory from `since` onward."""
    entries: list[Entry] = []
    for path in live_sessions(directory, since):
        entries += [e for e in session_entries(path) if e.timestamp >= since]
    return sorted(entries, key=lambda entry: (entry.timestamp, entry.session))


def models(directory: Path, since: datetime) -> set[str]:
    """Return every model that produced output from `since` onward.

    Subagents write their own transcripts next to the session's, and the
    AI-assisted block has to name their models too.
    """
    found: set[str] = set()
    for path in live_sessions(directory, since):
        subagents = sorted((directory / path.stem / "subagents").glob("*.jsonl"))
        for transcript in [path, *subagents]:
            for record in read_records(transcript):
                if record["type"] != "assistant":
                    continue
                model = (record.get("message") or {}).get("model")
                stamp = record.get("timestamp")
                if not model or model == "<synthetic>" or not stamp:
                    continue
                if datetime.fromisoformat(stamp) >= since:
                    found.add(model)
    return found


def render(
    entries: list[Entry],
    since: datetime,
    models: frozenset[str] | set[str] = frozenset(),
) -> str:
    names = sorted({entry.model for entry in entries} | set(models))
    if not entries:
        lines = [f"No prompts since {since.isoformat()}."]
        if names:
            lines.append(f"Models: {', '.join(names)}")
        return "\n".join(lines) + "\n"
    lines = [f"Prompts since {since.isoformat()}", f"Models: {', '.join(names)}"]
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


def slug(path: Path) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def transcript_directories(
    worktrees: list[Path], environ: Mapping[str, str]
) -> list[Path]:
    """Return the session directories of every checkout of this repository.

    Claude Code keeps one directory per working directory, so a session in a
    worktree is stored apart from the main checkout's. `worktrees` lists the
    main checkout first. Worktrees Claude Code created under it and has since
    removed are found by their directory name.
    """
    base = Path(environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    projects = base / "projects"
    candidates = [projects / slug(path) for path in worktrees]
    if worktrees:
        pattern = f"{slug(worktrees[0])}--claude-worktrees-*"
        candidates += sorted(projects.glob(pattern))
    return [path for path in dict.fromkeys(candidates) if path.is_dir()]


def worktrees() -> list[Path]:
    listing = git("worktree", "list", "--porcelain")
    return [
        Path(line.removeprefix("worktree "))
        for line in listing.splitlines()
        if line.startswith("worktree ")
    ]


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
        help="timestamp with UTC offset (default: author date of HEAD)",
    )
    parser.add_argument(
        "--transcripts",
        type=Path,
        action="append",
        help="directory with Claude Code session files, repeatable "
        "(default: those of every checkout of this repository)",
    )
    args = parser.parse_args(argv)
    try:
        since = parse_since(args.since or git("log", "-1", "--format=%aI"))
        directories = args.transcripts or transcript_directories(
            worktrees(), os.environ
        )
        if not directories:
            raise TranscriptError("no transcript directory for this repository")
        entries: list[Entry] = []
        found: set[str] = set()
        for directory in directories:
            if not directory.is_dir():
                raise TranscriptError(f"no transcript directory at {directory}")
            entries += collect(directory, since)
            found |= models(directory, since)
        entries.sort(key=lambda entry: (entry.timestamp, entry.session))
        sys.stdout.write(render(entries, since, found))
    except TranscriptError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
