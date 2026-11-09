"""Issue #64 - 범인 지목 FastAPI 통합 테스트."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from crimescene.api.app import create_app
from crimescene.scenario.case_truth import CaseTruth
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import EvidenceState, GameState
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository


def make_rules():
    scores = [1, 2, 3, 2, 3, 3, 2, 2, 1, 2]

    return {
        f"E{i:02d}": EvidenceRule(
            name=f"Test Evidence {i}",
            score=score,
            holder="C01",
            prerequisites=[],
            presentation=[],
            q=[],
        )
        for i, score in enumerate(scores, start=1)
    }


@pytest.fixture
def prepared_game(tmp_path):
    repository = SQLiteCase001Repository(tmp_path / "issue64.sqlite3")

    app = create_app(
        repository,
        session_secret="test-secret-" + "a" * 32,
    )

    app.state.dialogue_resources = SimpleNamespace(evidence_rules=make_rules())

    # 테스트 전용 가상 정답입니다. 실제 시나리오와 무관합니다.
    app.state.case_truth = CaseTruth(
        case_id="CASE-001",
        perpetrator_character_id="C03",
        motive="test motive",
        cause_of_death="test cause",
        crime_method="test method",
        crime_event_id="EVT-TEST",
    )

    with TestClient(app) as client:
        response = client.post("/api/games")
        assert response.status_code == 201

        session_id = response.json()["sessionId"]

        response = client.post(f"/api/games/{session_id}/prologue/complete")
        assert response.status_code == 200

        original = repository.load_state(session_id)

        # 증거 5개, 총점 11점을 충족하는 테스트 상태 생성
        evidence_ids = ("E01", "E02", "E03", "E04", "E05")

        updated = GameState.model_validate(
            {
                **original.model_dump(),
                "evidence": {
                    evidence_id: EvidenceState(stage="found").model_dump()
                    for evidence_id in evidence_ids
                },
                "score": 11,
                "revision": original.revision + 1,
            }
        )

        repository.commit_state(
            expected_state=original,
            updated_state=updated,
        )

        yield client, repository, session_id


def accuse(client, session_id, suspect_id, revision):
    return client.post(
        f"/api/games/{session_id}/accusations",
        json={
            "suspectId": suspect_id,
            "expectedRevision": revision,
        },
    )


def test_correct_accusation(prepared_game):
    client, repository, session_id = prepared_game
    revision = repository.load_state(session_id).revision

    response = accuse(client, session_id, "C03", revision)

    assert response.status_code == 200, response.text

    result = response.json()

    assert result["result"] == "CORRECT"
    assert result["attemptsLeft"] == 2
    assert result["game"]["phase"] == "FINISHED"
    assert result["game"]["outcome"] == "SUCCESS"


def test_three_wrong_accusations(prepared_game):
    client, repository, session_id = prepared_game

    for expected_attempts in (2, 1, 0):
        revision = repository.load_state(session_id).revision

        response = accuse(client, session_id, "C02", revision)

        assert response.status_code == 200, response.text

        result = response.json()

        assert result["result"] == "INCORRECT"
        assert result["attemptsLeft"] == expected_attempts

    assert result["game"]["phase"] == "FINISHED"
    assert result["game"]["outcome"] == "FAILURE"


def test_stale_revision_rejected(prepared_game):
    client, repository, session_id = prepared_game
    revision = repository.load_state(session_id).revision

    first = accuse(client, session_id, "C02", revision)
    assert first.status_code == 200

    # 이전 revision으로 동일 요청 재전송
    duplicate = accuse(client, session_id, "C02", revision)

    assert duplicate.status_code == 409
    assert repository.load_state(session_id).attempts_left == 2


def test_accusation_commits_once(prepared_game):
    client, repository, session_id = prepared_game

    before = repository.load_state(session_id)

    response = accuse(
        client,
        session_id,
        "C02",
        before.revision,
    )

    assert response.status_code == 200, response.text

    after = repository.load_state(session_id)

    # 단계 전환과 오답 판정을 단일 커밋으로 처리
    assert after.revision == before.revision + 1
    assert after.attempts_left == 2
    assert after.phase.value == "ACCUSATION"


def test_concurrent_accusations_only_one_commits(prepared_game):
    from concurrent.futures import ThreadPoolExecutor

    from crimescene.scenario.accusation_service import (
        submit_accusation_request_atomic,
    )

    client, repository, session_id = prepared_game
    before = repository.load_state(session_id)

    def submit():
        try:
            submit_accusation_request_atomic(
                session_id=session_id,
                suspect_id="C02",
                expected_revision=before.revision,
                repository=repository,
                truth=client.app.state.case_truth,
                evidence_rules=make_rules(),
            )
            return "SUCCESS"
        except ValueError:
            return "CONFLICT"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: submit(), range(2)))

    assert sorted(results) == ["CONFLICT", "SUCCESS"]

    after = repository.load_state(session_id)

    # 동시에 지목해도 기회는 한 번만 차감
    assert after.attempts_left == 2
    assert after.revision == before.revision + 1


def test_ending_blocked_before_finish(prepared_game):
    client, _, session_id = prepared_game

    response = client.get(f"/api/games/{session_id}/ending")

    assert response.status_code == 409


def test_success_ending(prepared_game):
    client, repository, session_id = prepared_game

    revision = repository.load_state(session_id).revision

    response = accuse(
        client,
        session_id,
        "C03",
        revision,
    )

    assert response.status_code == 200

    ending_response = client.get(f"/api/games/{session_id}/ending")

    assert ending_response.status_code == 200

    ending = ending_response.json()

    assert ending["outcome"] == "SUCCESS"
    assert ending["truth"]["perpetratorId"] == "C03"
    assert ending["game"]["phase"] == "FINISHED"


def test_failure_ending_hides_truth(prepared_game):
    client, repository, session_id = prepared_game

    for _ in range(3):
        revision = repository.load_state(session_id).revision

        response = accuse(
            client,
            session_id,
            "C02",
            revision,
        )

        assert response.status_code == 200

    ending_response = client.get(f"/api/games/{session_id}/ending")

    assert ending_response.status_code == 200

    ending = ending_response.json()

    assert ending["outcome"] == "FAILURE"
    assert ending["truth"] is None
    assert ending["game"]["attemptsLeft"] == 0
    assert ending["game"]["phase"] == "FINISHED"
