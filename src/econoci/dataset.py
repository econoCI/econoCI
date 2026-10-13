"""Read and write econoCI dataset files.

A dataset file is gzip-compressed JSON Lines. One schema table per record kind
drives both directions, so the reader's checks and the writer's key order
cannot drift apart. See specs/0001-data-model.md.
"""

import gzip
import json
import math
import os
import tempfile
import zlib
from collections.abc import Iterable, Iterator
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
# A small gzip file can expand to one enormous line. No record comes near
# this: the largest is a CI file stored as text.
MAX_LINE = 16 * 1024 * 1024


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
    ("root_actor_kind", "actor_kind"),
)


def _show(value: object) -> str:
    """Return a value from a file in a form that is safe to print.

    repr escapes control characters, so the value cannot alter a terminal or
    forge a log line, and the result is cut so one value cannot flood either.
    """
    text = repr(value)
    return text if len(text) <= 80 else text[:77] + "..."


class _DuplicateKey(Exception):
    pass


def _object(pairs: list[tuple[str, object]]) -> dict:
    row = dict(pairs)
    if len(row) != len(pairs):
        seen: set[str] = set()
        for key, _ in pairs:
            if key in seen:
                raise _DuplicateKey(key)
            seen.add(key)
    return row


def _constant(name: str) -> None:
    raise ValueError(f"{name} is not JSON")


def _encodable(text: str) -> bool:
    """False for text with a lone surrogate, which cannot be written as UTF-8."""
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _has_type(field: Field, value: object) -> bool:
    if field.type in ("string", "timestamp"):
        return isinstance(value, str)
    if field.type == "boolean":
        return isinstance(value, bool)
    if field.type == "integer":
        return type(value) is int
    if field.type == "number":
        # A literal like 1e999 parses to infinity, which JSON cannot hold.
        return type(value) in (int, float) and math.isfinite(value)
    # A tuple is what the model holds; a list is what JSON gives.
    return isinstance(value, list | tuple) and all(
        isinstance(item, str) for item in value
    )


def _decode(field: Field, value: object, where: str) -> object:
    if value is None:
        if field.nullable:
            return None
        raise DatasetError(f"{where}: {field.key} must not be null")
    if not _has_type(field, value):
        raise DatasetError(f"{where}: {field.key} is not {TYPE_NAMES[field.type]}")
    texts = [value] if isinstance(value, str) else []
    if field.type == "strings":
        texts = list(value)
    if not all(_encodable(text) for text in texts):
        raise DatasetError(f"{where}: {field.key} is not valid text")
    if field.values is not None and value not in field.values:
        raise DatasetError(f"{where}: {field.key} has the unknown value {_show(value)}")
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
    if not isinstance(kind, str) or kind not in SCHEMAS:
        raise DatasetError(f"{where}: unknown kind {_show(kind)}")
    record_type, fields = SCHEMAS[kind]
    extra = sorted(set(row) - {"kind"} - {field.key for field in fields})
    if extra:
        raise DatasetError(f"{where}: unknown key {_show(extra[0])}")
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
                raise DatasetError(f"{where}: {key} is missing in a pseudonymized file")
    if kind == "run":
        _check_root(record, where)


def _check_root(run: Run, where: str) -> None:
    """Reject root fields that contradict the run they belong to."""
    if run.parent_run == run.id:
        raise DatasetError(f"{where}: the run is its own parent")
    if run.parent_run is None and run.trigger != "upstream":
        for root_key, own_key in ROOT_OF:
            if getattr(run, root_key) != getattr(run, own_key):
                raise DatasetError(
                    f"{where}: {root_key} differs from {own_key} "
                    "although the run has no parent"
                )
        return
    # The root is the top of the chain, so it was not started by another run.
    if run.root_trigger == "upstream":
        raise DatasetError(
            f"{where}: root_trigger must not be upstream, "
            "use null when the chain could not be resolved"
        )
    if run.root_trigger is None:
        for key in ("root_platform_trigger", "root_actor", "root_actor_bot"):
            if getattr(run, key) is not None:
                raise DatasetError(
                    f"{where}: {key} must be null when root_trigger is null"
                )
    elif run.root_platform_trigger is None:
        raise DatasetError(
            f"{where}: root_platform_trigger must not be null "
            "when root_trigger is given"
        )


def _parse(lines: Iterable[str], source: str) -> Dataset:
    meta: Meta | None = None
    records: dict[str, list] = {kind: [] for kind in SCHEMAS if kind != "meta"}
    ids: dict[str, set[str]] = {"run": set(), "job": set(), "change_request": set()}
    job_lines: list[tuple[str, Job]] = []
    for number, line in enumerate(lines, 1):
        where = f"{source}:{number}"
        if len(line) > MAX_LINE:
            raise DatasetError(f"{where}: line longer than {MAX_LINE} characters")
        if not line.strip():
            raise DatasetError(f"{where}: empty line")
        try:
            row = json.loads(line, object_pairs_hook=_object, parse_constant=_constant)
        except _DuplicateKey as error:
            raise DatasetError(
                f"{where}: duplicate key {_show(error.args[0])}"
            ) from error
        except (ValueError, RecursionError) as error:
            # ValueError covers a syntax error, NaN and a number too long to parse.
            reason = getattr(error, "msg", None) or str(error) or type(error).__name__
            raise DatasetError(f"{where}: not JSON ({reason})") from error
        if not isinstance(row, dict):
            raise DatasetError(f"{where}: not a JSON object")
        if number == 1:
            if row.get("kind") != "meta":
                raise DatasetError(f"{where}: the first line must be the meta record")
            # Checked before the keys: a later format may have other keys.
            if row.get("format") != FORMAT:
                raise DatasetError(
                    f"{where}: format {_show(row.get('format'))} is not supported, "
                    f"this version reads format {FORMAT}"
                )
            meta = _record(row, where)[1]
            continue
        kind, record = _record(row, where)
        if kind == "meta":
            raise DatasetError(f"{where}: a second meta record")
        if kind in ids:
            if record.id in ids[kind]:
                raise DatasetError(f"{where}: duplicate {kind} id {_show(record.id)}")
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
                f"{where}: the job names the run {_show(job.run)}, "
                "which is not in the file"
            )
    return Dataset(
        meta=meta,
        runs=tuple(records["run"]),
        jobs=tuple(records["job"]),
        change_requests=tuple(records["change_request"]),
        configs=tuple(records["config"]),
    )


def _bounded(handle) -> Iterator[str]:
    """Yield the lines of a file without ever holding more than the limit.

    A line that exceeds the limit is passed on cut off, still too long, and
    the parser rejects it with its line number.
    """
    while line := handle.readline(MAX_LINE + 2):
        yield line.rstrip("\n")


def read(path: Path | str) -> Dataset:
    """Read a dataset file, or raise DatasetError naming the file and the line."""
    path = Path(path)
    try:
        with gzip.open(path, "rt", encoding="utf-8", newline="\n") as handle:
            return _parse(_bounded(handle), str(path))
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


def _lines(dataset: Dataset) -> Iterator[str]:
    """Yield the dataset's JSON lines in the order the specification gives."""
    groups = (
        ("meta", (dataset.meta,)),
        ("run", dataset.runs),
        ("job", dataset.jobs),
        ("change_request", dataset.change_requests),
        ("config", dataset.configs),
    )
    for kind, records in groups:
        for record in records:
            try:
                yield json.dumps(
                    _row(kind, record),
                    separators=(",", ":"),
                    ensure_ascii=False,
                    allow_nan=False,
                )
            except (TypeError, ValueError, AttributeError) as error:
                raise DatasetError(
                    f"a {kind} record cannot be written: {error}"
                ) from error


def dumps(dataset: Dataset) -> str:
    """Return the dataset as JSON Lines."""
    return "".join(line + "\n" for line in _lines(dataset))


def write(dataset: Dataset, path: Path | str) -> None:
    """Write a dataset file.

    An invalid dataset raises DatasetError and nothing is written. The file
    appears under its name only when it is complete, so a failed write leaves
    a previous file at that path untouched.
    """
    path = Path(path)
    # Two passes over the records, so the text is never held as one string.
    _parse(_lines(dataset), "dataset")
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with (
            os.fdopen(handle, "wb") as raw,
            # No file name and no time in the header: the bytes are reproducible.
            gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as packed,
        ):
            for line in _lines(dataset):
                packed.write(line.encode("utf-8") + b"\n")
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
