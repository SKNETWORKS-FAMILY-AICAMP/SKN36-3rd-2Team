"""Issue #165 - expanded ending API integration tests."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from crimescene.api.app import create_app
from crimescene.scenario.case_truth import CaseTruth
from crimescene.scenario.content_compiler import PROPOSED_SCORES
from crimescene.scenario.expanded_ending import (
    DEEP_FLAGS,
    FINAL_FLAG,
    ExpandedCaseTruth,
    ProofAxis,
)
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import GameState
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository

SELECTIONS = {
    "motive": ["E17", "E27"],
    "access": ["E21", "E23"],
    "timeline": ["E24", "E25"],
    "coverup": ["E20", "E26"],
}


@pytest.fixture
def runtime(tmp_path):
    repository = SQLiteCase001Repository(
        tmp_path / "ending.sqlite3"
    )

    app = create_app(
        repository,
        session_secret="issue165-ending-" + "x" * 40,
    )

    app.state.content_version = "case001_1120"

    legacy = dict(zip(
        [f"E{i:02d}" for i in range(1, 11)],
        [1, 2, 3, 2, 3, 3, 2, 2, 1, 2],
        strict=True,
    ))

    rules = {
        eid: EvidenceRule(
            name=f"Test {eid}",
            score=score,
            holder="C01",
            prerequisites=[],
            presentation=[],
            q=[],
        )
        for eid, score in {
            **legacy,
            **PROPOSED_SCORES,
        }.items()
    }

    app.state.case_truth = ExpandedCaseTruth(
        case_id="CASE-001",
        content_version="case001_1120",
        perpetrator_character_id="C02",
        motive="TEST MOTIVE",
        cause_of_death="TEST CAUSE",
        crime_method="TEST METHOD",
        crime_event_id="TEST EVENT",
        proof_axes=tuple(
            ProofAxis(
                axis=axis,
                evidence_options=(tuple(ids),),
            )
            for axis, ids in SELECTIONS.items()
        ),
    )

    app.state.dialogue_resources = SimpleNamespace(
        evidence_rules=rules,
    )

    with TestClient(app) as client:
        response = client.post("/api/games")
        assert response.status_code == 201

        sid = response.json()["sessionId"]

        response = client.post(
            f"/api/games/{sid}/prologue/complete"
        )

        assert response.status_code == 200

        yield app, client, repository, sid, rules


def prepare(runtime, *, full=True, deep=False, flags=()):
    _, _, repository, sid, rules = runtime

    before = repository.load_state(sid)

    ids = (
        [eid for eid in rules if eid != "E30"]
        if full else ["E01"]
    )

    if deep:
        ids.append("E30")

    state = GameState.model_validate({
        **before.model_dump(),
        "current_chapter": "CH04",
        "unlocked_chapters": [
            "CH00", "CH01", "CH02", "CH03", "CH04",
        ],
        "unlocked_characters": ["C01", "C02"],
        "evidence": {
            eid: {"stage": "found"}
            for eid in ids
        },
        "score": sum(rules[eid].score for eid in ids),
        "flags": list(flags),
        "revision": before.revision + 1,
    })

    repository.commit_state(
        expected_state=before,
        updated_state=state,
    )


def reconstruct(runtime, selections=None):
    _, client, repository, sid, _ = runtime

    state = repository.load_state(sid)

    return client.post(
        f"/api/games/{sid}/reconstruction",
        json={
            "expectedRevision": state.revision,
            "selections": (
                SELECTIONS if selections is None
                else selections
            ),
        },
    )


def accuse(runtime, suspect="C02"):
    _, client, repository, sid, _ = runtime

    state = repository.load_state(sid)

    return client.post(
        f"/api/games/{sid}/accusations",
        json={
            "expectedRevision": state.revision,
            "suspectId": suspect,
        },
    )


def ending(runtime):
    _, client, _, sid, _ = runtime

    response = client.get(
        f"/api/games/{sid}/ending"
    )

    assert response.status_code == 200

    return response.json()


def test_no_evidence_ending(runtime):
    prepare(runtime, full=False)

    _, client, repository, sid, _ = runtime
    state = repository.load_state(sid)

    response = client.post(
        f"/api/games/{sid}/give-up",
        json={"expectedRevision": state.revision},
    )

    assert response.status_code == 200
    assert ending(runtime)["outcome"] == "NO_EVIDENCE"
    assert ending(runtime)["truth"] is None


def test_unsolved_ending(runtime):
    prepare(runtime)

    for _ in range(3):
        assert accuse(runtime, "C01").status_code == 200

    assert ending(runtime)["outcome"] == "UNSOLVED"
    assert ending(runtime)["truth"] is None


def test_estimated_ending(runtime):
    prepare(runtime)

    assert accuse(runtime).status_code == 200

    result = ending(runtime)

    assert result["outcome"] == "ESTIMATED"
    assert result["truth"] is None
    assert result["deepEligible"] is False


def test_full_ending(runtime):
    prepare(runtime)

    response = reconstruct(runtime)

    assert response.status_code == 200
    assert response.json()["accepted"] is True

    assert accuse(runtime).status_code == 200

    result = ending(runtime)

    assert result["outcome"] == "FULL"
    assert result["truth"]["perpetratorId"] == "C02"


def test_deep_ending(runtime):
    prepare(runtime, deep=True, flags=DEEP_FLAGS)

    assert reconstruct(runtime).status_code == 200
    assert accuse(runtime).status_code == 200

    result = ending(runtime)

    assert result["outcome"] == "DEEP"
    assert result["deepEligible"] is True


def test_deep_without_consent_is_full(runtime):
    prepare(
        runtime,
        deep=True,
        flags=DEEP_FLAGS - {
            "consent_and_safety_verified"
        },
    )

    assert reconstruct(runtime).status_code == 200
    assert accuse(runtime).status_code == 200

    assert ending(runtime)["outcome"] == "FULL"


def test_wrong_reconstruction_not_granted(runtime):
    prepare(runtime)

    wrong = {
        **SELECTIONS,
        "motive": ["E01", "E02"],
    }

    response = reconstruct(runtime, wrong)

    assert response.status_code == 200
    assert response.json()["accepted"] is False

    _, _, repository, sid, _ = runtime

    assert FINAL_FLAG not in repository.load_state(sid).flags


def test_three_independent_axes_sufficient(runtime):
    prepare(runtime)

    selections = {
        key: value
        for key, value in SELECTIONS.items()
        if key != "coverup"
    }

    response = reconstruct(runtime, selections)

    assert response.status_code == 200
    assert response.json()["accepted"] is True


def test_reconstruction_idempotent(runtime):
    prepare(runtime)

    assert reconstruct(runtime).status_code == 200

    _, _, repository, sid, _ = runtime

    before = repository.load_state(sid)
    response = reconstruct(runtime)

    assert response.status_code == 200
    assert response.json()["created"] is False
    assert repository.load_state(sid) == before


def test_legacy_truth_cannot_finish_expanded_game(runtime):
    prepare(runtime)

    app, _, repository, sid, _ = runtime

    app.state.case_truth = CaseTruth(
        case_id="CASE-001",
        perpetrator_character_id="C01",
        motive="LEGACY SECRET",
        cause_of_death="LEGACY SECRET",
        crime_method="LEGACY SECRET",
        crime_event_id="LEGACY EVENT",
    )

    before = repository.load_state(sid)

    assert accuse(runtime).status_code == 409
    assert repository.load_state(sid) == before


def test_ending_hidden_before_finish(runtime):
    prepare(runtime)

    _, client, _, sid, _ = runtime

    response = client.get(
        f"/api/games/{sid}/ending"
    )

    assert response.status_code == 409
