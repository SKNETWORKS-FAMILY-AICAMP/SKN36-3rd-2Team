"""이슈 #217 - 최종 재구성 및 엔딩 통합 검증."""

from itertools import combinations

import pytest
from fastapi.testclient import TestClient

from crimescene.api.app import create_app
from crimescene.scenario.expanded_ending import (
    DEEP_FLAGS,
    FINAL_FLAG,
    ProofAxis,
)
from crimescene.scenario.schemas.game_state import (
    GamePhase,
)
from crimescene.trigger.atomic_dialogue import (
    SQLiteCase001Repository,
)

from test_expanded_ending_http import (
    runtime,
    prepare,
    reconstruct,
    accuse,
    ending,
    finish_image_test_game,
    SELECTIONS,
)

from test_day9_investigation_progression import (
    runtime as investigation_runtime,
    prepare_branches,
    get_state,
    get_game,
)


ENDING_CODES = (
    "NO_EVIDENCE",
    "UNSOLVED",
    "ESTIMATED",
    "FULL",
    "DEEP",
)


def current_state(runtime):
    _, _, repository, sid, _ = runtime
    return repository.load_state(sid)


def assert_unchanged(runtime, before):
    _, _, repository, sid, _ = runtime

    assert repository.load_state(sid) == before

    selection = repository.load_selection(sid)

    assert selection is not None
    assert selection[1] == before.revision


def test_day9_natural_no_evidence_ending(
    investigation_runtime,
):
    """DB에 증거를 직접 삽입하지 않고 증거 부족 엔딩에 진입한다."""

    env = investigation_runtime

    _, client, repository, sid, _ = env

    prepare_branches(env)

    before = get_state(env)

    assert set(before.evidence) == {
        "E11", "E19", "E20"
    }

    game = get_game(env)

    assert game["canAccuse"] is False
    assert game["attemptsLeft"] == 3

    # 증거가 부족한 상태의 지목은 기회를 차감하지 않는다.
    denied = client.post(
        f"/api/games/{sid}/accusations",
        json={
            "suspectId": "C01",
            "expectedRevision": before.revision,
        },
    )

    assert denied.status_code == 200, denied.text
    assert denied.json()["result"] == "NOT_ENOUGH_EVIDENCE"
    assert denied.json()["attemptsLeft"] == 3

    assert repository.load_state(sid) == before

    assert client.get(
        f"/api/games/{sid}/ending"
    ).status_code == 409

    response = client.post(
        f"/api/games/{sid}/give-up",
        json={
            "expectedRevision": before.revision,
        },
    )

    assert response.status_code == 200, response.text

    result = response.json()

    assert result["ending"] == "NO_EVIDENCE"
    assert result["revision"] == before.revision + 1

    saved = repository.load_state(sid)

    assert saved.phase == GamePhase.FINISHED
    assert saved.ending_code == "NO_EVIDENCE"
    assert saved.attempts_left == 3
    assert saved.evidence == before.evidence
    assert saved.score == before.score

    final = client.get(
        f"/api/games/{sid}/ending"
    )

    assert final.status_code == 200
    assert final.json()["outcome"] == "NO_EVIDENCE"
    assert final.json()["truth"] is None


@pytest.mark.parametrize(
    "axes",
    list(combinations(SELECTIONS, 3)),
)
def test_day9_each_three_independent_axes(
    runtime,
    axes,
):
    """테스트 원장에서 독립적인 세 항목의 모든 조합을 검증한다."""

    prepare(runtime)

    before = current_state(runtime)

    selected = {
        axis: SELECTIONS[axis]
        for axis in axes
    }

    response = reconstruct(runtime, selected)

    assert response.status_code == 200, response.text

    result = response.json()

    assert result["accepted"] is True
    assert result["created"] is True
    assert result["revision"] == before.revision + 1

    after = current_state(runtime)

    assert FINAL_FLAG in after.flags
    assert after.phase == GamePhase.INVESTIGATION
    assert after.evidence == before.evidence
    assert after.score == before.score
    assert after.attempts_left == before.attempts_left

    retry = reconstruct(runtime, selected)

    assert retry.status_code == 200
    assert retry.json()["accepted"] is True
    assert retry.json()["created"] is False
    assert retry.json()["revision"] == after.revision

    assert_unchanged(runtime, after)


@pytest.mark.parametrize(
    ("selections", "expected_status"),
    [
        (
            {
                "motive": SELECTIONS["motive"],
                "access": SELECTIONS["access"],
            },
            422,
        ),
        (
            {
                "motive": SELECTIONS["motive"],
                "access": SELECTIONS["access"],
                "unknown": ["E01", "E02"],
            },
            422,
        ),
        (
            {
                **SELECTIONS,
                "motive": ["E17", "E17"],
            },
            422,
        ),
        (
            {
                **SELECTIONS,
                "motive": ["E17"],
            },
            422,
        ),
        (
            {
                **SELECTIONS,
                "motive": ["E17", "E30"],
            },
            403,
        ),
    ],
)
def test_day9_invalid_reconstruction_preserves_state(
    runtime,
    selections,
    expected_status,
):
    """잘못된 재구성 요청은 진행 상태를 변경하지 않는다."""

    prepare(runtime)

    before = current_state(runtime)

    response = reconstruct(runtime, selections)

    assert response.status_code == expected_status, response.text

    assert FINAL_FLAG not in current_state(runtime).flags
    assert_unchanged(runtime, before)


def test_day9_overlapping_axes_not_independent(runtime):
    """승인 조합이어도 독립적인 증거 집합이 아니면 거부한다."""

    prepare(runtime)

    app, _, _, _, _ = runtime

    overlapping = {
        "motive": ["E17", "E27"],
        "access": ["E17", "E23"],
        "timeline": ["E17", "E25"],
        "coverup": ["E20", "E26"],
    }

    original = app.state.case_truth

    # 독립성 검증 전용 가상 원장이다.
    app.state.case_truth = original.model_copy(
        update={
            "proof_axes": tuple(
                ProofAxis(
                    axis=axis,
                    evidence_options=(tuple(ids),),
                )
                for axis, ids in overlapping.items()
            ),
        },
    )

    before = current_state(runtime)

    selections = {
        axis: overlapping[axis]
        for axis in ("motive", "access", "timeline")
    }

    response = reconstruct(runtime, selections)

    assert response.status_code == 200, response.text
    assert response.json()["accepted"] is False
    assert response.json()["created"] is False

    assert_unchanged(runtime, before)


def test_day9_accusation_attempts_and_replay(runtime):
    """오답 지목 3회와 이전 Revision 재시도를 검증한다."""

    prepare(runtime)

    _, client, _, sid, _ = runtime

    for remaining in (2, 1, 0):
        before = current_state(runtime)

        response = accuse(runtime, "C01")

        assert response.status_code == 200, response.text

        payload = response.json()

        assert payload["result"] == "INCORRECT"
        assert payload["attemptsLeft"] == remaining

        after = current_state(runtime)

        assert after.revision == before.revision + 1
        assert after.attempts_left == remaining
        assert after.evidence == before.evidence
        assert after.score == before.score

        assert payload["game"]["revision"] == after.revision

        assert {
            "type": "ACCUSATION_RESULT"
        } in payload["game"]["events"]

        stale = client.post(
            f"/api/games/{sid}/accusations",
            json={
                "suspectId": "C01",
                "expectedRevision": before.revision,
            },
        )

        assert stale.status_code == 409

        assert_unchanged(runtime, after)

        if remaining:
            assert after.phase == GamePhase.INVESTIGATION

            assert client.get(
                f"/api/games/{sid}/ending"
            ).status_code == 409

        else:
            assert after.phase == GamePhase.FINISHED
            assert after.ending_code == "UNSOLVED"

    final = ending(runtime)

    assert final["outcome"] == "UNSOLVED"
    assert final["truth"] is None

    before = current_state(runtime)

    assert accuse(runtime, "C01").status_code == 409

    assert_unchanged(runtime, before)


def test_day9_missing_truth_fails_closed(runtime):
    """정본 판정 원장이 연결되지 않으면 판정을 수행하지 않는다."""

    prepare(runtime)

    app, _, _, _, _ = runtime

    # 실제 런타임의 원장 미연결 상황을 재현한다.
    del app.state.case_truth

    before = current_state(runtime)

    response = reconstruct(runtime)

    assert response.status_code == 503
    assert_unchanged(runtime, before)

    response = accuse(runtime)

    assert response.status_code == 503
    assert_unchanged(runtime, before)


def test_day9_stale_reconstruction(runtime):
    """오래된 Revision으로 재구성을 제출할 수 없다."""

    prepare(runtime)

    _, client, _, sid, _ = runtime

    before = current_state(runtime)

    response = client.post(
        f"/api/games/{sid}/reconstruction",
        json={
            "expectedRevision": before.revision - 1,
            "selections": SELECTIONS,
        },
    )

    assert response.status_code == 409
    assert_unchanged(runtime, before)


def test_day9_ending_cross_session_denied(runtime):
    """다른 플레이어의 재구성, 지목 및 엔딩 조회를 차단한다."""

    prepare(runtime)

    app, _, _, sid, _ = runtime

    before = current_state(runtime)

    with TestClient(app) as stranger:
        assert stranger.post(
            "/api/games"
        ).status_code == 201

        base = f"/api/games/{sid}"

        reconstruction = stranger.post(
            base + "/reconstruction",
            json={
                "expectedRevision": before.revision,
                "selections": SELECTIONS,
            },
        )

        assert reconstruction.status_code == 404

        accusation = stranger.post(
            base + "/accusations",
            json={
                "expectedRevision": before.revision,
                "suspectId": "C02",
            },
        )

        assert accusation.status_code == 404

        assert stranger.get(
            base + "/ending"
        ).status_code == 404

        assert_unchanged(runtime, before)

        # 실제 종료 후에도 타 세션 엔딩은 공개하지 않는다.
        assert reconstruct(runtime).status_code == 200
        assert accuse(runtime).status_code == 200

        assert stranger.get(
            base + "/ending"
        ).status_code == 404


@pytest.mark.parametrize(
    "missing",
    ["E30", *sorted(DEEP_FLAGS)],
)
def test_day9_deep_missing_requirement_is_full(
    runtime,
    missing,
):
    """심화 엔딩의 필수 조건 중 하나라도 없으면 FULL을 반환한다."""

    flags = DEEP_FLAGS - {missing}

    prepare(
        runtime,
        deep=missing != "E30",
        flags=flags,
    )

    assert reconstruct(runtime).status_code == 200

    response = accuse(runtime)

    assert response.status_code == 200, response.text

    result = ending(runtime)

    assert result["outcome"] == "FULL"
    assert result["deepEligible"] is False

    assert current_state(runtime).deep_eligible is False


@pytest.mark.parametrize("code", ENDING_CODES)
def test_day9_ending_persistence_and_disclosure(
    runtime,
    tmp_path,
    code,
):
    """테스트 원장으로 엔딩 판정 후 영속 상태와 공개 범위를 검증한다."""

    app, client, _, sid, _ = runtime

    # 테스트용 증거 및 플래그 상태를 사용한다.
    # 실제 정본 콘텐츠의 자연 플레이 검증은 아니다.
    finish_image_test_game(runtime, code)

    before = current_state(runtime)
    original = ending(runtime)

    assert before.phase == GamePhase.FINISHED
    assert before.ending_code == code

    assert original["outcome"] == code
    assert original["deepEligible"] == (code == "DEEP")

    if code in ("FULL", "DEEP"):
        assert original["truth"] is not None

        assert original["truth"]["perpetratorId"] == (
            app.state.case_truth.perpetrator_character_id
        )

    else:
        assert original["truth"] is None

        for secret in (
            "TEST MOTIVE",
            "TEST CAUSE",
            "TEST METHOD",
        ):
            assert secret not in str(original)

    restored_repository = SQLiteCase001Repository(
        tmp_path / "ending.sqlite3"
    )

    restored_app = create_app(
        restored_repository,
        session_secret="issue165-ending-" + "x" * 40,
    )

    for attribute in (
        "content_version",
        "dialogue_resources",
        "case_truth",
    ):
        setattr(
            restored_app.state,
            attribute,
            getattr(app.state, attribute),
        )

    with TestClient(restored_app) as resumed:
        resumed.cookies.update(client.cookies)

        restored = resumed.get(
            f"/api/games/{sid}/ending"
        )

        assert restored.status_code == 200, restored.text
        assert restored.json() == original

        state_response = resumed.get(
            f"/api/games/{sid}"
        )

        assert state_response.status_code == 200

        payload = state_response.json()

        assert payload["phase"] == "FINISHED"
        assert payload["canAccuse"] is False
        assert payload["revision"] == before.revision

        assert payload["attemptsLeft"] == before.attempts_left

        assert payload["collection"]["score"] == before.score

        assert restored_repository.load_state(sid) == before

        # 종료된 게임에 대한 추가 판정은 불가능하다.
        rejected = resumed.post(
            f"/api/games/{sid}/accusations",
            json={
                "expectedRevision": before.revision,
                "suspectId": "C01",
            },
        )

        assert rejected.status_code == 409

        rejected = resumed.post(
            f"/api/games/{sid}/give-up",
            json={
                "expectedRevision": before.revision,
            },
        )

        assert rejected.status_code == 409

        assert restored_repository.load_state(sid) == before

    assert_unchanged(runtime, before)
