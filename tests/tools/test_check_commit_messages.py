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


def test_path_instead_of_a_range_is_an_error(repo, tmp_path, capsys):
    (tmp_path / "notes").write_text("not a revision", encoding="utf-8")
    assert check.main(["notes"]) == 2
    assert "git log failed" in capsys.readouterr().err
