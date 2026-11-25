import pytest
from fastapi.testclient import TestClient

from crimescene.api.app import create_app
from crimescene.api.expanded_chapter_runtime import (
    BRANCH_REQUIREMENTS,
    FINAL_REQUIREMENTS,
    FINAL_FLAGS,
    build_expanded_chapter_rules,
)
from crimescene.scenario.chapter_progress import (
    ChapterUnlockRule,
)
from crimescene.scenario.schemas.game_state import GameState
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository


@pytest.fixture
def runtime(tmp_path):
    repository = SQLiteCase001Repository(
        tmp_path / "expanded_chapters.sqlite3"
    )

    app = create_app(
        repository,
        session_secret="expanded-chapter-tests-" + "x" * 40,
    )

    app.state.content_version = "case001_1120"
    app.state.chapter_unlock_rules = build_expanded_chapter_rules()

    with TestClient(app) as client:
        response = client.post("/api/games")
        assert response.status_code == 201

        sid = response.json()["sessionId"]

        yield client, repository, sid


def advance(runtime, chapter):
    client, repository, sid = runtime

    state = repository.load_state(sid)

    return client.post(
        f"/api/games/{sid}/chapter/advance",
        json={
            "expectedRevision": state.revision,
            "targetChapter": chapter,
        },
    )


def start(runtime):
    client, _, sid = runtime

    response = client.post(
        f"/api/games/{sid}/prologue/complete"
    )

    assert response.status_code == 200
    assert advance(runtime, "CH01").status_code == 200


def seed(runtime, evidence=(), flags=()):
    _, repository, sid = runtime

    before = repository.load_state(sid)

    updated = GameState.model_validate({
        **before.model_dump(),
        "evidence": {
            **before.model_dump()["evidence"],
            **{
                eid: {"stage": "found"}
                for eid in evidence
            },
        },
        "flags": sorted(set(before.flags) | set(flags)),
        "revision": before.revision + 1,
    })

    repository.commit_state(
        expected_state=before,
        updated_state=updated,
    )


def test_ch01_requires_prologue(runtime):
    assert advance(runtime, "CH01").status_code == 409

    start(runtime)

    _, repository, sid = runtime
    assert repository.load_state(sid).current_chapter == "CH01"


def test_branch_requires_initial_evidence(runtime):
    start(runtime)

    _, repository, sid = runtime

    before = repository.load_state(sid)

    for chapter in ("CH02", "CH03"):
        assert advance(runtime, chapter).status_code == 409

    assert repository.load_state(sid) == before


@pytest.mark.parametrize(
    "first,second",
    [("CH02", "CH03"), ("CH03", "CH02")],
)
def test_both_branch_orders_and_revisit(runtime, first, second):
    start(runtime)

    seed(runtime, BRANCH_REQUIREMENTS)

    assert advance(runtime, first).status_code == 200

    # Cannot skip the other investigation branch.
    assert advance(runtime, "CH04").status_code == 409

    assert advance(runtime, second).status_code == 200

    _, repository, sid = runtime

    before = repository.load_state(sid)

    assert advance(runtime, first).status_code == 200

    after = repository.load_state(sid)

    assert after.current_chapter == first
    assert after.unlocked_chapters == before.unlocked_chapters
    assert after.score == before.score
    assert after.revision == before.revision + 1

    assert advance(runtime, second).status_code == 200


@pytest.mark.parametrize(
    "missing",
    sorted(FINAL_REQUIREMENTS),
)
def test_ch04_requires_every_evidence(runtime, missing):
    start(runtime)
    seed(runtime, BRANCH_REQUIREMENTS)

    assert advance(runtime, "CH02").status_code == 200
    assert advance(runtime, "CH03").status_code == 200

    _, repository, sid = runtime

    # E20 was previously collected for branch access.
    # Remove one item only in this isolated negative-test fixture.
    current = repository.load_state(sid)

    updated = GameState.model_validate({
        **current.model_dump(),
        "evidence": {
            eid: {"stage": "found"}
            for eid in (
                BRANCH_REQUIREMENTS | FINAL_REQUIREMENTS
            ) - {missing}
        },
        "flags": sorted(FINAL_FLAGS),
        "revision": current.revision + 1,
    })

    repository.commit_state(
        expected_state=current,
        updated_state=updated,
    )

    assert advance(runtime, "CH04").status_code == 409
    assert repository.load_state(sid) == updated


@pytest.mark.parametrize("missing", sorted(FINAL_FLAGS))
def test_ch04_requires_every_flag(runtime, missing):
    start(runtime)
    seed(runtime, BRANCH_REQUIREMENTS)

    assert advance(runtime, "CH02").status_code == 200
    assert advance(runtime, "CH03").status_code == 200

    seed(
        runtime,
        FINAL_REQUIREMENTS,
        FINAL_FLAGS - {missing},
    )

    assert advance(runtime, "CH04").status_code == 409


def test_ch04_transition(runtime):
    start(runtime)
    seed(runtime, BRANCH_REQUIREMENTS)

    assert advance(runtime, "CH03").status_code == 200
    assert advance(runtime, "CH02").status_code == 200

    seed(runtime, FINAL_REQUIREMENTS, FINAL_FLAGS)

    assert advance(runtime, "CH04").status_code == 200

    _, repository, sid = runtime
    final = repository.load_state(sid)

    assert final.current_chapter == "CH04"

    assert set(final.unlocked_chapters) == {
        "CH00", "CH01", "CH02", "CH03", "CH04",
    }

    # E29 must remain obtainable after entering CH04.
    assert "E29" not in final.evidence
    assert "E30" not in final.evidence

    # No return to investigation branches after CH04.
    assert advance(runtime, "CH03").status_code == 409


def test_empty_rule_remains_forbidden():
    with pytest.raises(ValueError):
        ChapterUnlockRule(target_chapter="CH04")


def test_prologue_rule_restricted_to_ch01():
    with pytest.raises(ValueError):
        ChapterUnlockRule(
            target_chapter="CH04",
            requires_completed_prologue=True,
        )


def test_rules_are_immutable():
    rules = build_expanded_chapter_rules()

    with pytest.raises(TypeError):
        rules["CH04"] = rules["CH01"]
