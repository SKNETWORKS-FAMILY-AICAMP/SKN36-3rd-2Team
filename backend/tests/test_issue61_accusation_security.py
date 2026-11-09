"""Issue #61: unlocked-only accusation and authoritative ending behavior."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from crimescene.api.app import create_app
from crimescene.scenario.case_truth import CaseTruth
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import EvidenceState, GameState
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository


@pytest.fixture
def prepared_game(tmp_path):
    repository = SQLiteCase001Repository(tmp_path / "issue61.sqlite3")
    app = create_app(repository, session_secret="issue61-test-" + "x" * 40)
    scores = [1, 2, 3, 2, 3, 3, 2, 2, 1, 2]
    app.state.dialogue_resources = SimpleNamespace(
        evidence_rules={
            f"E{index:02d}": EvidenceRule(
                name=f"테스트 증거 {index}",
                score=score,
                holder="C01",
                prerequisites=[],
                presentation=[],
                q=[],
            )
            for index, score in enumerate(scores, start=1)
        }
    )
    # 테스트 전용 정답이며 실제 사건 원장은 사용하지 않습니다.
    app.state.case_truth = CaseTruth(
        case_id="CASE-001",
        perpetrator_character_id="C03",
        motive="test motive",
        cause_of_death="test cause",
        crime_method="test method",
        crime_event_id="EVT-TEST",
    )
    with TestClient(app) as client:
        created = client.post("/api/games")
        assert created.status_code == 201
        sid = created.json()["sessionId"]
        started = client.post(f"/api/games/{sid}/prologue/complete")
        assert started.status_code == 200
        original = repository.load_state(sid)
        updated = GameState.model_validate(
            {
                **original.model_dump(),
                "evidence": {
                    f"E{i:02d}": EvidenceState(stage="found").model_dump()
                    for i in range(1, 6)
                },
                "score": 11,
                "revision": original.revision + 1,
            }
        )
        repository.commit_state(expected_state=original, updated_state=updated)
        yield client, repository, sid


def _accuse(client, sid, suspect, revision):
    return client.post(
        f"/api/games/{sid}/accusations",
        json={"suspectId": suspect, "expectedRevision": revision},
    )


def test_locked_suspect_is_blocked_without_mutation(prepared_game):
    client, repository, sid = prepared_game
    before = repository.load_state(sid)
    assert before.unlocked_characters == ["C01"]

    response = _accuse(client, sid, "C03", before.revision)

    assert response.status_code == 403, response.text
    assert repository.load_state(sid) == before
    assert client.get(f"/api/games/{sid}/ending").status_code == 409


def test_unlocked_suspect_reaches_success_ending(prepared_game):
    client, repository, sid = prepared_game
    original = repository.load_state(sid)
    updated = GameState.model_validate(
        {
            **original.model_dump(),
            "unlocked_characters": ["C01", "C03"],
            "revision": original.revision + 1,
        }
    )
    repository.commit_state(expected_state=original, updated_state=updated)

    response = _accuse(client, sid, "C03", updated.revision)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["result"] == "CORRECT"
    assert result["game"]["phase"] == "FINISHED"

    ending = client.get(f"/api/games/{sid}/ending")
    assert ending.status_code == 200, ending.text
    assert ending.json()["truth"]["perpetratorId"] == "C03"
    assert repository.load_state(sid).attempts_left == 2


def test_not_enough_evidence_keeps_attempt_and_revision(prepared_game):
    client, repository, sid = prepared_game
    original = repository.load_state(sid)
    insufficient = GameState.model_validate(
        {
            **original.model_dump(),
            "evidence": {},
            "score": 0,
            "revision": original.revision + 1,
        }
    )
    repository.commit_state(expected_state=original, updated_state=insufficient)

    response = _accuse(client, sid, "C01", insufficient.revision)
    assert response.status_code == 200, response.text
    assert response.json()["result"] == "NOT_ENOUGH_EVIDENCE"
    assert repository.load_state(sid) == insufficient
    assert client.get(f"/api/games/{sid}/ending").status_code == 409
