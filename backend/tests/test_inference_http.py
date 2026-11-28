"""Issue #165 - objective and inference API tests."""

import pytest
from fastapi.testclient import TestClient

from crimescene.api.app import create_app
from crimescene.scenario.investigation_progress import (
    InferenceRule,
    ObjectiveRule,
)
from crimescene.scenario.schemas.game_state import GameState
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository


@pytest.fixture
def runtime(tmp_path):
    repository = SQLiteCase001Repository(
        tmp_path / "inference.sqlite3"
    )

    app = create_app(
        repository,
        session_secret="issue165-inference-" + "x" * 40,
    )

    app.state.content_version = "case001_1120"

    app.state.approved_inference_rules = (
        InferenceRule(
            rule_id="LINK-001",
            inference_id="INF_ACCESS_WINDOW",
            chapter="CH03",
            evidence_ids=frozenset({"E21", "E23"}),
        ),
    )

    app.state.approved_objective_rules = (
        ObjectiveRule(
            objective_id="OBJ_FIND_CARD_USER",
            chapter="CH03",
            required_evidence=frozenset({"E21"}),
            target_evidence=frozenset({"E23"}),
        ),
        ObjectiveRule(
            objective_id="OBJ_RECONSTRUCT_ROUTE",
            chapter="CH03",
            required_evidence=frozenset({"E23"}),
            target_evidence=frozenset({"E24", "E25"}),
        ),
    )

    with TestClient(app) as client:
        response = client.post("/api/games")

        assert response.status_code == 201

        sid = response.json()["sessionId"]

        response = client.post(
            f"/api/games/{sid}/prologue/complete"
        )

        assert response.status_code == 200

        state = repository.load_state(sid)

        updated = GameState.model_validate({
            **state.model_dump(),
            "current_chapter": "CH03",
            "unlocked_chapters": [
                "CH00", "CH01", "CH03",
            ],
            "evidence": {
                "E21": {"stage": "found"},
                "E23": {"stage": "found"},
                "E25": {"stage": "found"},
            },
            "score": 7,
            "revision": state.revision + 1,
        })

        repository.commit_state(
            expected_state=state,
            updated_state=updated,
        )

        yield app, client, repository, sid


def infer(
    runtime,
    evidence=None,
    revision=None,
    **extra,
):
    _, client, repository, sid = runtime

    state = repository.load_state(sid)

    return client.post(
        f"/api/games/{sid}/inferences",
        json={
            "evidenceIds": (
                ["E21", "E23"]
                if evidence is None
                else evidence
            ),
            "expectedRevision": (
                state.revision
                if revision is None
                else revision
            ),
            **extra,
        },
    )


def test_objective_status(runtime):
    _, client, _, sid = runtime

    response = client.get(
        f"/api/games/{sid}/objectives"
    )

    assert response.status_code == 200

    assert response.json()["items"] == [
        {
            "objectiveId": "OBJ_FIND_CARD_USER",
            "status": "COMPLETED",
            "chapter": "CH03",
            "title": "임시 카드 사용자 조사",
            "description": (
                "카드 사용 기록과 다른 자료를 비교해 사용자를 좁혀 보세요."
            ),
        },
        {
            "objectiveId": "OBJ_RECONSTRUCT_ROUTE",
            "status": "ACTIVE",
            "chapter": "CH03",
            "title": "사건 당시 동선 재구성",
            "description": (
                "계단 주변의 이동 시각과 경로를 비교하세요."
            ),
        },
    ]


def test_valid_inference_persists(runtime):
    _, _, repository, sid = runtime

    before = repository.load_state(sid)

    response = infer(runtime)

    assert response.status_code == 200
    assert response.json()["accepted"] is True
    assert response.json()["created"] is True

    after = repository.load_state(sid)

    assert "INF_ACCESS_WINDOW" in after.flags
    assert after.revision == before.revision + 1
    assert after.score == before.score


def test_duplicate_inference_is_idempotent(runtime):
    assert infer(runtime).status_code == 200

    _, _, repository, sid = runtime
    before = repository.load_state(sid)

    response = infer(runtime)

    assert response.status_code == 200
    assert response.json()["created"] is False
    assert repository.load_state(sid) == before


def test_wrong_evidence_pair(runtime):
    _, _, repository, sid = runtime

    before = repository.load_state(sid)

    response = infer(runtime, ["E21", "E25"])

    assert response.status_code == 200
    assert response.json()["accepted"] is False
    assert repository.load_state(sid) == before


def test_uncollected_evidence_denied(runtime):
    response = infer(runtime, ["E21", "E24"])

    assert response.status_code == 403


def test_duplicate_evidence_denied(runtime):
    response = infer(runtime, ["E21", "E21"])

    assert response.status_code == 422


def test_client_cannot_grant_inference(runtime):
    response = infer(
        runtime,
        flags=["INF_DEEP_GATE"],
    )

    assert response.status_code == 422


def test_stale_revision_denied(runtime):
    _, _, repository, sid = runtime

    state = repository.load_state(sid)

    response = infer(
        runtime,
        revision=state.revision - 1,
    )

    assert response.status_code == 409


def test_unapproved_rules_do_not_execute(runtime):
    app, _, repository, sid = runtime

    app.state.approved_inference_rules = ()

    before = repository.load_state(sid)

    response = infer(runtime)

    assert response.status_code == 200
    assert response.json()["accepted"] is False
    assert repository.load_state(sid) == before


def test_protected_inference_cannot_be_registered():
    with pytest.raises(ValueError):
        InferenceRule(
            rule_id="LINK-030",
            inference_id="INF_DEEP_GATE",
            chapter="CH04",
            evidence_ids=frozenset({"E14", "E30"}),
        )


def test_other_player_cannot_submit(runtime):
    app, _, repository, sid = runtime

    before = repository.load_state(sid)

    with TestClient(app) as stranger:
        response = stranger.post(
            f"/api/games/{sid}/inferences",
            json={
                "evidenceIds": ["E21", "E23"],
                "expectedRevision": before.revision,
            },
        )

    assert response.status_code == 404
    assert repository.load_state(sid) == before

def test_objective_display_catalog():
    """공개 대상 목표와 표시 문구의 범위가 일치한다."""

    import re

    from crimescene.api.expanded_progression_runtime import (
        OBJECTIVE_SELECTION,
    )
    from crimescene.api.inference_http import (
        OBJECTIVE_DISPLAY_TEXT,
    )

    assert len(OBJECTIVE_DISPLAY_TEXT) == 11
    assert set(OBJECTIVE_DISPLAY_TEXT) == OBJECTIVE_SELECTION

    for title, description in OBJECTIVE_DISPLAY_TEXT.values():
        assert title.strip()
        assert description.strip()

        combined = title + " " + description

        assert not re.search(
            r"\bE(?:0[1-9]|[12][0-9]|30)\b",
            combined,
        )

        for forbidden in (
            "ACT_",
            "INF_",
            "K-C",
            "POL-",
            "STORY_",
        ):
            assert forbidden not in combined


@pytest.mark.parametrize(
    ("objective_id", "chapter", "required_evidence"),
    [
        (
            "OBJ_CHECK_SCHOLARSHIP",
            "CH02",
            frozenset({"E21"}),
        ),
        (
            "OBJ_FIND_SHUTDOWN_REASON",
            "CH03",
            frozenset({"E22"}),
        ),
    ],
)
def test_objective_locked_content_not_exposed(
    runtime,
    objective_id,
    chapter,
    required_evidence,
):
    """잠긴 챕터 또는 선행 증거 미충족 목표를 반환하지 않는다."""

    from crimescene.api.inference_http import (
        OBJECTIVE_DISPLAY_TEXT,
    )

    app, client, repository, sid = runtime

    rule = ObjectiveRule(
        objective_id=objective_id,
        chapter=chapter,
        required_evidence=required_evidence,
        target_evidence=frozenset({"E24"}),
    )

    app.state.approved_objective_rules += (rule,)

    before = repository.load_state(sid)

    response = client.get(
        f"/api/games/{sid}/objectives"
    )

    assert response.status_code == 200

    items = response.json()["items"]

    assert len(items) == 2
    assert objective_id not in {
        item["objectiveId"] for item in items
    }

    title, description = OBJECTIVE_DISPLAY_TEXT[objective_id]

    assert all(
        item["title"] != title
        and item["description"] != description
        for item in items
    )

    assert repository.load_state(sid) == before


def test_objective_unlocked_previous_chapter_visible(runtime):
    """현재 챕터와 달라도 이미 해금된 목표는 유지한다."""

    app, client, _, sid = runtime

    app.state.approved_objective_rules += (
        ObjectiveRule(
            objective_id="OBJ_FIND_STUDENT_RECORD",
            chapter="CH01",
            required_evidence=frozenset(),
            target_evidence=frozenset({"E12"}),
        ),
    )

    response = client.get(
        f"/api/games/{sid}/objectives"
    )

    assert response.status_code == 200

    items = {
        item["objectiveId"]: item
        for item in response.json()["items"]
    }

    previous = items["OBJ_FIND_STUDENT_RECORD"]

    assert previous["chapter"] == "CH01"
    assert previous["status"] == "ACTIVE"
    assert previous["title"] == "학생 기록 조사"


def test_objective_unknown_display_uses_safe_fallback(runtime):
    """상세 문구 미등록 시 안전한 기본 문구를 사용한다."""

    app, client, _, sid = runtime

    app.state.approved_objective_rules += (
        ObjectiveRule(
            objective_id="OBJ_TEST_FUTURE_DISPLAY",
            chapter="CH03",
            required_evidence=frozenset({"E21"}),
            target_evidence=frozenset({"E24"}),
        ),
    )

    response = client.get(
        f"/api/games/{sid}/objectives"
    )

    assert response.status_code == 200

    items = {
        item["objectiveId"]: item
        for item in response.json()["items"]
    }

    assert items["OBJ_TEST_FUTURE_DISPLAY"] == {
        "objectiveId": "OBJ_TEST_FUTURE_DISPLAY",
        "status": "ACTIVE",
        "chapter": "CH03",
        "title": "수사 목표",
        "description": "현재 공개된 자료와 인물을 조사하세요.",
    }


def test_objective_display_read_only(runtime):
    """반복 조회로 게임 및 NPC 선택 상태를 변경하지 않는다."""

    _, client, repository, sid = runtime

    before = repository.load_state(sid)
    selection = repository.load_selection(sid)

    url = f"/api/games/{sid}/objectives"

    first = client.get(url)
    second = client.get(url)

    assert first.status_code == 200
    assert second.status_code == 200

    assert first.json() == second.json()

    assert first.headers["cache-control"] == (
        "private, no-store"
    )

    for item in first.json()["items"]:
        assert set(item) == {
            "objectiveId",
            "status",
            "chapter",
            "title",
            "description",
        }

    assert repository.load_state(sid) == before
    assert repository.load_selection(sid) == selection


def test_objective_display_other_session_denied(runtime):
    """다른 플레이어의 수사 목표를 조회할 수 없다."""

    app, _, repository, sid = runtime

    before = repository.load_state(sid)

    with TestClient(app) as stranger:
        created = stranger.post("/api/games")

        assert created.status_code == 201

        response = stranger.get(
            f"/api/games/{sid}/objectives"
        )

        assert response.status_code == 404
        assert "items" not in response.json()
        assert repository.load_state(sid) == before
