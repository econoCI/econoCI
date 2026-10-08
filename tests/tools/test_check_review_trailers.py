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
    assert not review.is_reviewed(
        "Merge work\n\nReviewed-by: Model X <noreply@anthropic.com>\n"
    )


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


def test_ai_assisted_merge_commit_needs_a_trailer_itself(git, capsys):
    # A merge commit can carry changes of its own, such as a conflict resolution.
    branch(git, "work", "Fix a typo")
    merge(git, "work", f"Merge work\n\n{AI}")
    assert review.main(["base..main"]) == 1
    out = capsys.readouterr().out
    assert "Merge work: AI-assisted merge commit, no Reviewed-by" in out


def test_ai_assisted_merge_commit_passes_with_a_trailer(git):
    branch(git, "work", "Fix a typo")
    merge(git, "work", f"Merge work\n\n{REVIEWED}\n{AI}")
    assert review.main(["base..main"]) == 0
