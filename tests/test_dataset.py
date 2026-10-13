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
    values = {
        "id": "r2",
        "trigger": "upstream",
        "platform_trigger": "parent_pipeline",
        "root_trigger": "schedule",
        "root_platform_trigger": "schedule",
        "root_actor": "nightly-bot",
        "root_actor_bot": True,
        "parent_run": "r1",
    }
    return run(**{**values, **changes})


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


def test_line_separators_inside_a_text_survive(tmp_path):
    # Only a line feed ends a record. Other separators can occur in a CI file.
    text = "a:\r\n  script: one\u2028two\x85three\x0bfour\n"
    first = dataset.read(save(tmp_path, [meta(), config(text=text)]))
    dataset.write(first, tmp_path / "copy.jsonl.gz")
    assert dataset.read(tmp_path / "copy.jsonl.gz").configs[0].text == text


def raw_line(row, **replacements):
    """Return a row as a JSON line with some values replaced by raw JSON text."""
    line = json.dumps(row)
    for key, text in replacements.items():
        line = line.replace(json.dumps(row[key]), text, 1)
    return line + "\n"


@pytest.mark.parametrize(
    ("rows", "line", "message"),
    [
        ([meta(), {"kind": []}], 2, "unknown kind []"),
        ([meta(), {"kind": {}}], 2, "unknown kind {}"),
        ([meta(), run(), raw_line(job(), attempt="9" * 5000)], 3, "not JSON"),
        ([meta(), "[" * 100000 + "\n"], 2, "not JSON"),
        ([meta(), run(), raw_line(job(), queued_seconds="NaN")], 3, "not JSON"),
        ([meta(), run(), raw_line(job(), queued_seconds="-Infinity")], 3, "not JSON"),
        (
            [meta(), run(), raw_line(job(), queued_seconds="1e999")],
            3,
            "queued_seconds is not a number",
        ),
        ([meta(), '{"kind":"run","kind":"job"}\n'], 2, "duplicate key 'kind'"),
        ([meta(), raw_line(run(), commit='"abc","id":"zzz"')], 2, "duplicate key 'id'"),
        (
            [meta(), raw_line(config(), text='"\\ud83d broken"')],
            2,
            "text is not valid text",
        ),
        ([meta(), run(), run(id="r2", parent_run="r2")], 3, "its own parent"),
        (
            [meta(), child_run(root_trigger="upstream")],
            2,
            "root_trigger must not be upstream",
        ),
        (
            [meta(), child_run(root_trigger=None)],
            2,
            "root_platform_trigger must be null",
        ),
        (
            [meta(), child_run(root_trigger=None, root_platform_trigger=None)],
            2,
            "root_actor must be null",
        ),
        (
            [meta(), child_run(root_platform_trigger=None)],
            2,
            "root_platform_trigger must not be null",
        ),
    ],
)
def test_more_reading_errors_name_the_line(tmp_path, rows, line, message):
    path = save(tmp_path, rows)
    with pytest.raises(dataset.DatasetError) as caught:
        dataset.read(path)
    assert f"data.jsonl.gz:{line}: " in str(caught.value)
    assert message in str(caught.value)


def test_top_level_run_must_repeat_its_stored_kind_as_root(tmp_path):
    rows = [meta(), run(actor_kind="bot", root_actor_kind="person")]
    with pytest.raises(dataset.DatasetError, match="root_actor_kind differs"):
        dataset.read(save(tmp_path, rows))


def test_a_failed_write_keeps_the_previous_file(tmp_path):
    good = dataset.read(save(tmp_path, [meta(), run()]))
    target = tmp_path / "kept.jsonl.gz"
    dataset.write(good, target)
    before = target.read_bytes()
    bad_run = model.Run(**{**vars(good.runs[0]), "trigger": "cron"})
    with pytest.raises(dataset.DatasetError):
        dataset.write(model.Dataset(meta=good.meta, runs=(bad_run,)), target)
    assert target.read_bytes() == before
    assert [path.name for path in tmp_path.iterdir() if "kept" in path.name] == [
        "kept.jsonl.gz"
    ]


def test_an_interrupted_write_keeps_the_previous_file(tmp_path, monkeypatch):
    good = dataset.read(save(tmp_path, [meta(), run()]))
    target = tmp_path / "kept.jsonl.gz"
    dataset.write(good, target)
    before = target.read_bytes()

    def fail(*arguments, **options):
        raise OSError("disk full")

    monkeypatch.setattr(dataset.os, "replace", fail)
    with pytest.raises(OSError, match="disk full"):
        dataset.write(good, target)
    assert target.read_bytes() == before
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "data.jsonl.gz",
        "kept.jsonl.gz",
    ]


@pytest.mark.parametrize(
    "changes",
    [
        {"queued_seconds": float("nan")},
        {"duration_seconds": float("inf")},
        {"tags": {"docker"}},
        {"id": b"j1"},
    ],
)
def test_write_refuses_values_json_cannot_hold(tmp_path, changes):
    good = dataset.read(save(tmp_path, [meta(), run(), job()]))
    bad_job = model.Job(**{**vars(good.jobs[0]), **changes})
    bad = model.Dataset(meta=good.meta, runs=good.runs, jobs=(bad_job,))
    target = tmp_path / "bad.jsonl.gz"
    with pytest.raises(dataset.DatasetError):
        dataset.write(bad, target)
    assert not target.exists()


def test_the_gzip_header_carries_no_time_and_no_name(tmp_path):
    data = dataset.read(save(tmp_path, [meta()]))
    dataset.write(data, tmp_path / "one.jsonl.gz")
    header = (tmp_path / "one.jsonl.gz").read_bytes()[:10]
    assert header[3] == 0  # no flags, so no stored file name
    assert header[4:8] == b"\x00\x00\x00\x00"  # no modification time


def test_round_trip_of_stored_kinds_fractions_and_offsets(tmp_path):
    rows = [
        meta(pseudonymized=True, collected_at="2026-01-02T13:00:00.250+01:00"),
        run(
            actor="u_1f2e3d",
            actor_bot=True,
            actor_kind="bot",
            root_actor="u_1f2e3d",
            root_actor_bot=True,
            root_actor_kind="bot",
        ),
        child_run(
            root_trigger=None,
            root_platform_trigger=None,
            root_actor=None,
            root_actor_bot=None,
            actor_kind="person",
            root_actor_kind="unknown",
        ),
        change_request(author_kind="person", merger_kind="bot"),
    ]
    first = dataset.read(save(tmp_path, rows))
    assert first.meta.collected_at.microsecond == 250000
    dataset.write(first, tmp_path / "copy.jsonl.gz")
    second = dataset.read(tmp_path / "copy.jsonl.gz")
    assert second == first
    assert dataset.dumps(second) == dataset.dumps(first)
    lines = [json.loads(line) for line in dataset.dumps(first).splitlines()]
    assert list(lines[0]) == list(meta())
    assert list(lines[1]).index("actor_kind") == list(lines[1]).index("actor_bot") + 1
    assert lines[2]["root_actor_kind"] == "unknown"
