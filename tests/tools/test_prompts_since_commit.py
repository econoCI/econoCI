import json
import os
import subprocess
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


QUEUED = {
    "type": "queued_command",
    "commandMode": "prompt",
    "origin": {"kind": "human"},
}


def test_queued_prompt_is_printed(tmp_path):
    queued = {
        "type": "attachment",
        "timestamp": T1,
        "attachment": {**QUEUED, "prompt": "also add a test"},
    }
    other = {"type": "attachment", "timestamp": T1, "attachment": {"type": "date"}}
    write(tmp_path, "aaaaaaaa-1", [queued, other])
    assert texts(psc.collect(tmp_path, SINCE)) == [("prompt", "also add a test")]


def test_queued_prompt_without_text_is_an_error(tmp_path):
    queued = {
        "type": "attachment",
        "timestamp": T1,
        "attachment": dict(QUEUED),
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


def test_transcript_directories_cover_every_checkout(tmp_path):
    projects = tmp_path / "projects"
    main = projects / "-home-pat-dev-my-project"
    removed = projects / "-home-pat-dev-my-project--claude-worktrees-old-one"
    other = projects / "-home-pat-wt-feature"
    unrelated = projects / "-home-pat-dev-my-project-two"
    for directory in (main, removed, other, unrelated):
        directory.mkdir(parents=True)
    worktrees = [
        Path("/home/pat/dev/my.project"),
        Path("/home/pat/wt/feature"),
        Path("/home/pat/wt/never-used"),
    ]
    found = psc.transcript_directories(worktrees, {"CLAUDE_CONFIG_DIR": str(tmp_path)})
    assert found == [main, other, removed]


def test_transcript_directories_default_to_the_home_directory():
    found = psc.transcript_directories([], {})
    assert found == []


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


def test_queued_notifications_and_agent_messages_are_left_out(tmp_path):
    def queued(**fields):
        return {
            "type": "attachment",
            "timestamp": T1,
            "attachment": {"type": "queued_command", "prompt": "text", **fields},
        }

    write(
        tmp_path,
        "aaaaaaaa-1",
        [
            queued(commandMode="task-notification"),
            queued(
                commandMode="task-notification", origin={"kind": "task-notification"}
            ),
            queued(commandMode="prompt", origin={"kind": "peer"}, isMeta=True),
            queued(commandMode="prompt", origin={"kind": "peer"}),
            queued(commandMode="prompt", origin={"kind": "human"}, isMeta=True),
            queued(commandMode="prompt"),
        ],
    )
    assert psc.collect(tmp_path, SINCE) == []


def test_queued_harness_text_is_left_out(tmp_path):
    record = {
        "type": "attachment",
        "timestamp": T1,
        "attachment": {
            **QUEUED,
            "prompt": "<task-notification>done</task-notification>",
        },
    }
    write(tmp_path, "aaaaaaaa-1", [record])
    assert psc.collect(tmp_path, SINCE) == []


def test_message_from_another_agent_is_left_out(tmp_path):
    write(tmp_path, "aaaaaaaa-1", [user(T1, "report", origin={"kind": "peer"})])
    assert psc.collect(tmp_path, SINCE) == []


def test_prompt_marked_as_human_is_printed(tmp_path):
    write(tmp_path, "aaaaaaaa-1", [user(T1, "add a rule", origin={"kind": "human"})])
    assert texts(psc.collect(tmp_path, SINCE)) == [("prompt", "add a rule")]


@pytest.mark.parametrize(
    "marker",
    [*psc.HARNESS_PREFIXES, "[Request interrupted by user]"],
)
def test_harness_markers_are_left_out(tmp_path, marker):
    write(tmp_path, "aaaaaaaa-1", [user(T1, f"{marker} more text")])
    assert psc.collect(tmp_path, SINCE) == []


def test_interrupt_for_tool_use_is_left_out(tmp_path):
    write(
        tmp_path, "aaaaaaaa-1", [user(T1, "[Request interrupted by user for tool use]")]
    )
    assert psc.collect(tmp_path, SINCE) == []


def test_feedback_on_a_rejected_tool_call_is_printed(tmp_path):
    write(
        tmp_path,
        "aaaaaaaa-1",
        [
            assistant(
                T1, [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {}}]
            ),
            user(
                T2,
                [
                    {
                        "type": "tool_result",
                        "tool_use_id": "t1",
                        "is_error": True,
                        "content": "Rejected. the user said:\nuse tabs",
                    }
                ],
                userFeedback="use tabs",
            ),
        ],
    )
    assert texts(psc.collect(tmp_path, SINCE)) == [("feedback", "use tabs")]


@pytest.mark.parametrize(
    "kind",
    [
        "agent-name",
        "artifact-autoreact-ledger",
        "artifact-comment-monitor",
        "continued-in",
        "custom-title",
        "frame-link",
        "pr-link",
        "relocated",
        "worktree-state",
    ],
)
def test_record_types_of_other_sessions_are_known(tmp_path, kind):
    write(tmp_path, "aaaaaaaa-1", [{"type": kind}, user(T1, "first")])
    assert texts(psc.collect(tmp_path, SINCE)) == [("prompt", "first")]


def test_last_line_cut_inside_a_character_is_skipped(tmp_path):
    path = write(tmp_path, "aaaaaaaa-1", [user(T1, "first")])
    cut = '{"type": "user", "message": "caf\u00e9'.encode("utf-8").decode(
        "unicode_escape"
    )
    path.write_bytes(path.read_bytes() + cut.encode("utf-8")[:-1])
    assert texts(psc.collect(tmp_path, SINCE)) == [("prompt", "first")]


def test_models_include_subagents_and_respect_the_cutoff(tmp_path):
    write(
        tmp_path,
        "aaaaaaaa-1",
        [reply(BEFORE, model="model-old-0"), user(T1, "first"), reply(T2)],
    )
    subagents = tmp_path / "aaaaaaaa-1" / "subagents"
    subagents.mkdir(parents=True)
    write(
        subagents,
        "agent-1",
        [reply(BEFORE, model="model-early-0"), reply(T3, model="model-z-3")],
    )
    assert psc.models(tmp_path, SINCE) == {"model-x-1", "model-z-3"}


def test_render_lists_models_without_a_prompt():
    entries = [psc.Entry(SINCE, "aaaaaaaa", "prompt", "first", "model-x-1")]
    out = psc.render(entries, SINCE, {"model-z-3"})
    assert "Models: model-x-1, model-z-3" in out.splitlines()
    assert psc.render([], SINCE, {"model-z-3"}) == (
        "No prompts since 2026-01-02T12:00:00+00:00.\nModels: model-z-3\n"
    )


def test_main_reads_several_directories(tmp_path, capsys):
    first, second = tmp_path / "one", tmp_path / "two"
    first.mkdir()
    second.mkdir()
    write(first, "aaaaaaaa-1", [user(T2, "second"), reply(T3)])
    write(second, "bbbbbbbb-2", [user(T1, "first"), reply(T3, model="model-y-2")])
    code = psc.main(
        [
            "--since",
            "2026-01-02T12:00:00Z",
            "--transcripts",
            str(first),
            "--transcripts",
            str(second),
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert out.index("    first") < out.index("    second")
    assert "Models: model-x-1, model-y-2" in out


def test_default_cutoff_is_the_author_date_of_head(tmp_path, monkeypatch, capsys):
    # An amend or a rebase moves the committer date and keeps the author date.
    repo = tmp_path / "repo"
    sessions = tmp_path / "sessions"
    repo.mkdir()
    sessions.mkdir()
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.org",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.org",
        "GIT_AUTHOR_DATE": "2026-01-02T12:00:00+00:00",
        "GIT_COMMITTER_DATE": "2026-01-02T13:00:00+00:00",
    }
    for command in (
        ["git", "init", "-b", "main"],
        ["git", "-c", "commit.gpgsign=false", "commit", "--allow-empty", "-m", "x"],
    ):
        subprocess.run(command, cwd=repo, env=env, check=True, capture_output=True)
    write(sessions, "aaaaaaaa-1", [user(BEFORE, "too early"), user(T1, "add a rule")])
    monkeypatch.chdir(repo)
    assert psc.main(["--transcripts", str(sessions)]) == 0
    out = capsys.readouterr().out
    # The earlier prompt is shown apart, as the last entry before the cut-off.
    assert out.index("too early") < out.index("Prompts since")
    assert out.index("Prompts since") < out.index("    add a rule")


def test_prompt_sent_by_a_program_is_left_out(tmp_path):
    write(
        tmp_path,
        "aaaaaaaa-1",
        [
            user(T1, "Review this change.", promptSource="sdk"),
            user(T2, "add a rule", promptSource="typed"),
            user(T3, "yes, do that", promptSource="suggestion_accepted"),
        ],
    )
    assert texts(psc.collect(tmp_path, SINCE)) == [
        ("prompt", "add a rule"),
        ("prompt", "yes, do that"),
    ]


def test_last_entry_before_the_cutoff_is_found(tmp_path):
    # The message that approves a commit often also asks for the next step.
    write(
        tmp_path,
        "aaaaaaaa-1",
        [user("2026-01-02T11:00:00.000Z", "oldest"), user(T1, "after")],
    )
    write(tmp_path, "bbbbbbbb-2", [user(BEFORE, "approved, now add CI"), reply(T2)])
    previous = psc.last_before(tmp_path, SINCE)
    assert (previous.session, previous.text) == ("bbbbbbbb", "approved, now add CI")


def test_no_entry_before_the_cutoff(tmp_path):
    write(tmp_path, "aaaaaaaa-1", [user(T1, "after")])
    assert psc.last_before(tmp_path, SINCE) is None


def test_render_shows_the_entry_before_the_cutoff_apart():
    before = psc.Entry(
        datetime(2026, 1, 2, 11, 59, 59, tzinfo=UTC),
        "bbbbbbbb",
        "prompt",
        "approved, now add CI",
        "model-x-1",
    )
    after = psc.Entry(SINCE, "aaaaaaaa", "prompt", "first", "model-x-1")
    assert psc.render([after], SINCE, previous=before).splitlines() == [
        "Last entry before the cut-off:",
        "2026-01-02T11:59:59Z  bbbbbbbb  prompt  model-x-1",
        "    approved, now add CI",
        "",
        "Prompts since 2026-01-02T12:00:00+00:00",
        "Models: model-x-1",
        "",
        "2026-01-02T12:00:00Z  aaaaaaaa  prompt  model-x-1",
        "    first",
    ]
