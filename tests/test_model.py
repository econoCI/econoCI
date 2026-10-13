from datetime import UTC, datetime

import pytest

from econoci import model

T = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)


def run(**changes):
    values = {
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
        "created_at": T,
        "finished_at": T,
    }
    return model.Run(**{**values, **changes})


def change_request(**changes):
    values = {
        "id": "c1",
        "repository": "acme/shop",
        "source_ref": "feature/cart",
        "state": "merged",
        "platform_state": "merged",
        "author": "pat",
        "author_bot": False,
        "merger": "sam",
        "merger_bot": False,
        "auto_merge": False,
        "created_at": T,
        "merged_at": T,
    }
    return model.ChangeRequest(**{**values, **changes})


def test_a_stored_kind_wins_over_everything():
    assert model.derive_kind("renovate-bot", True, stored="person") == "person"
    assert model.derive_kind(None, None, stored="bot") == "bot"


def test_no_name_is_unknown():
    assert model.derive_kind(None, None) == "unknown"
    assert model.derive_kind(None, True) == "unknown"


def test_the_platform_flag_makes_a_bot():
    assert model.derive_kind("pat", True) == "bot"


def test_an_ordinary_name_is_a_person():
    assert model.derive_kind("pat", False) == "person"
    assert model.derive_kind("pat", None) == "person"


@pytest.mark.parametrize(
    ("matching", "not_matching"),
    [
        ("build-bot", "bob"),
        ("Renovate-Runner", "renata"),
        ("dependabot", "dependable"),
        ("project_123_x", "my_project_123"),
        ("group_45_x", "subgroup_45"),
        ("shop-service", "servus"),
        ("deployer", "deputy"),
        ("ci-token-user", "tolkien"),
    ],
)
def test_bot_patterns(matching, not_matching):
    assert model.derive_kind(matching, False) == "bot"
    assert model.derive_kind(not_matching, False) == "person"


def test_every_bot_pattern_has_a_case():
    assert len(model.BOT_PATTERNS) == 8


@pytest.mark.parametrize("ref", ["renovate/pytest-9.x", "Dependabot/pip/urllib3"])
def test_a_bot_branch_makes_the_author_a_bot(ref):
    assert model.derive_kind("pat", False, source_ref=ref) == "bot"
    assert model.derive_kind("pat", False, source_ref="feature/cart") == "person"


def test_run_kinds_are_derived():
    record = run(actor="pat", root_actor="renovate-bot", root_actor_bot=None)
    assert record.kind_of_actor() == "person"
    assert record.kind_of_root_actor() == "bot"


def test_run_kinds_prefer_the_stored_value():
    record = run(actor="u_1f2e3d", actor_kind="bot", root_actor_kind="person")
    assert record.kind_of_actor() == "bot"
    assert record.kind_of_root_actor() == "person"


def test_run_with_unresolved_root_has_an_unknown_root_actor():
    record = run(trigger="upstream", root_trigger=None, root_actor=None)
    assert record.kind_of_root_actor() == "unknown"


def test_change_request_author_uses_the_source_ref_and_merger_does_not():
    record = change_request(source_ref="renovate/pytest-9.x")
    assert record.kind_of_author() == "bot"
    assert record.kind_of_merger() == "person"


def test_change_request_without_merger():
    record = change_request(merger=None, merger_bot=None, merged_at=None)
    assert record.kind_of_merger() == "unknown"


def test_records_are_immutable():
    record = run()
    with pytest.raises(AttributeError):
        record.trigger = "schedule"


def test_dataset_groups_records():
    meta = model.Meta(
        format=1,
        platform="gitlab",
        collector="test 0",
        collected_at=T,
        period_start=T,
        period_end=T,
        pseudonymized=False,
        repositories_seen=1,
        repositories_with_runs=1,
        repositories_unreadable=0,
    )
    dataset = model.Dataset(meta=meta, runs=(run(),))
    assert dataset.runs[0].id == "r1"
    assert dataset.jobs == ()
