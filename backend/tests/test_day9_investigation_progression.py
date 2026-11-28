"""이슈 #212 - 현장 조사 및 챕터 진행 통합 테스트."""

from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from crimescene.api.app import create_app
from crimescene.api.django_content_client import DjangoContentClient
from crimescene.api.expanded_chapter_runtime import (
    build_expanded_chapter_rules,
)
from crimescene.api.investigation_http import ACTION_CANDIDATES
from crimescene.scenario.content_compiler import (
    PROPOSED_SCORES,
    proposed_routes,
)
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository


CH01_ACTIONS = (
    ("inspect-e11-a", "E11"),
    ("inspect-e19-a", "E19"),
    ("inspect-e20-a", "E20"),
)

CH02_ACTIONS = (
    ("inspect-e12-a", "E12"),
    ("inspect-e13-a", "E13"),
    ("inspect-e14-a", "E14"),
)

CH03_ACTIONS = (
    ("inspect-e21-a", "E21"),
    ("inspect-sensor-record", "E23"),
    ("inspect-emergency-door-record", "E25"),
)

CHAPTER_ACTIONS = {
    "CH01": CH01_ACTIONS,
    "CH02": CH02_ACTIONS,
    "CH03": CH03_ACTIONS,
}

ALL_ACTIONS = (
    CH01_ACTIONS
    + CH02_ACTIONS
    + CH03_ACTIONS
)


@pytest.fixture
def runtime(tmp_path):
    """외부 승인 서비스만 모의 처리하는 독립 실행 환경."""

    repository = SQLiteCase001Repository(
        tmp_path / "day9-progression.sqlite3"
    )

    app = create_app(
        repository,
        session_secret="day9-progression-" + "x" * 40,
    )

    app.state.content_version = "case001_1120"
    app.state.chapter_unlock_rules = (
        build_expanded_chapter_rules()
    )

    scores = dict(zip(
        [f"E{i:02d}" for i in range(1, 11)],
        [1, 2, 3, 2, 3, 3, 2, 2, 1, 2],
        strict=True,
    ))

    scores.update(PROPOSED_SCORES)

    rules = {
        eid: EvidenceRule(
            name=f"테스트 증거 {eid}",
            score=score,
            holder="C01",
            prerequisites=[],
            presentation=[],
            q=[],
        )
        for eid, score in scores.items()
    }

    app.state.dialogue_resources = SimpleNamespace(
        evidence_rules=rules,
    )

    actions = {
        action_id: ACTION_CANDIDATES[action_id]
        for action_id, _ in ALL_ACTIONS
    }

    # 테스트 전용 승인 설정이며 실제 공개 승인이 아니다.
    app.state.approved_investigation_actions = frozenset(
        actions
    )

    app.state.approved_acquisition_routes = {
        eid: proposed_routes(
            eid,
            actions[action_id].chapter,
        )
        for action_id, eid in ALL_ACTIONS
    }

    scene_chapters = {
        action.scene_id: action.chapter
        for action in actions.values()
    }

    evidence_prerequisites = {
        action.evidence_id: sorted(action.required_evidence)
        for action in actions.values()
    }

    settings = {
        "scene_approved": True,
        "evidence_approved": True,
    }

    def handler(request):
        parts = request.url.path.strip("/").split("/")

        if "scenes" in parts:
            index = parts.index("scenes")
            scene_id = parts[index + 1]

            if (
                not settings["scene_approved"]
                or scene_id not in scene_chapters
            ):
                return httpx.Response(404)

            return httpx.Response(
                200,
                json={
                    "scene_id": scene_id,
                    "chapter": scene_chapters[scene_id],
                    "title": "테스트 장면",
                    "scene_text": "테스트 조사 내용",
                },
            )

        if "evidence" in parts:
            index = parts.index("evidence")
            eid = parts[index + 1]

            if (
                not settings["evidence_approved"]
                or eid not in evidence_prerequisites
            ):
                return httpx.Response(404)

            return httpx.Response(
                200,
                json={
                    "evidence_id": eid,
                    "prerequisites": (
                        evidence_prerequisites[eid]
                    ),
                    "player_unlock_verification_required": True,
                },
            )

        return httpx.Response(404)

    django = DjangoContentClient(
        base_url="http://127.0.0.1:8002",
        token="x" * 40,
        transport=httpx.MockTransport(handler),
    )

    app.state.django_content_client = django

    try:
        with TestClient(app) as client:
            created = client.post("/api/games")

            assert created.status_code == 201

            sid = created.json()["sessionId"]

            # 게임 상태나 획득 증거를 DB에 직접 삽입하지 않는다.
            yield app, client, repository, sid, settings

    finally:
        django.close()


def get_state(runtime):
    _, _, repository, sid, _ = runtime
    return repository.load_state(sid)


def get_game(runtime):
    _, client, _, sid, _ = runtime

    response = client.get(f"/api/games/{sid}")

    assert response.status_code == 200, response.text

    return response.json()


def get_actions(runtime):
    _, client, _, sid, _ = runtime

    before = get_state(runtime)

    response = client.get(
        f"/api/games/{sid}/locations"
    )

    assert response.status_code == 200, response.text

    payload = response.json()

    assert payload["revision"] == before.revision
    assert payload["currentChapter"] == before.current_chapter
    assert get_state(runtime) == before

    actions = {}

    for location in payload["locations"]:
        for item in location["actions"]:
            actions[item["actionId"]] = item["available"]

        for space in location["subspaces"]:
            for item in space["actions"]:
                actions[item["actionId"]] = item["available"]

    return actions


def advance(runtime, chapter, revision=None):
    _, client, _, sid, _ = runtime

    state = get_state(runtime)

    return client.post(
        f"/api/games/{sid}/chapter/advance",
        json={
            "expectedRevision": (
                state.revision
                if revision is None
                else revision
            ),
            "targetChapter": chapter,
        },
    )


def investigate(runtime, action_id, revision=None):
    _, client, _, sid, _ = runtime

    state = get_state(runtime)

    return client.post(
        f"/api/games/{sid}/investigations/{action_id}",
        json={
            "expectedRevision": (
                state.revision
                if revision is None
                else revision
            ),
        },
    )


def start_ch01(runtime):
    _, client, _, sid, _ = runtime

    completed = client.post(
        f"/api/games/{sid}/prologue/complete"
    )

    assert completed.status_code == 200, completed.text

    response = advance(runtime, "CH01")

    assert response.status_code == 200, response.text
    assert response.json()["currentChapter"] == "CH01"


def assert_game_consistency(runtime):
    _, _, repository, sid, _ = runtime

    state = get_state(runtime)
    game = get_game(runtime)

    assert game["sessionId"] == sid
    assert game["revision"] == state.revision
    assert game["currentChapter"] == state.current_chapter
    assert game["collection"]["score"] == state.score

    assert game["unlockedChapters"] == (
        state.unlocked_chapters
    )

    assert game["unlockedCharacters"] == (
        state.unlocked_characters
    )

    assert repository.load_selection(sid) == (
        game["activeCharacterId"],
        state.revision,
    )


def collect_action(runtime, action_id, eid):
    before = get_state(runtime)

    actions = get_actions(runtime)

    assert actions[action_id] is True

    response = investigate(runtime, action_id)

    assert response.status_code == 200, response.text

    result = response.json()
    after = get_state(runtime)

    assert result["evidenceId"] == eid
    assert result["created"] is True
    assert result["revision"] == before.revision + 1
    assert result["score"] == after.score

    assert set(after.evidence) == (
        set(before.evidence) | {eid}
    )

    assert after.score == (
        before.score + PROPOSED_SCORES[eid]
    )

    assert after.revision == result["revision"]

    assert_game_consistency(runtime)


def prepare_branches(runtime):
    start_ch01(runtime)

    for action_id, eid in CH01_ACTIONS:
        collect_action(runtime, action_id, eid)


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("CH02", "CH03"),
        ("CH03", "CH02"),
    ],
)
def test_day9_investigation_branch_flow(
    runtime,
    first,
    second,
):
    """실제 HTTP 요청을 통한 초기 조사 및 양방향 분기 진행."""

    prepare_branches(runtime)

    for chapter in (first, second):
        before = get_state(runtime)

        response = advance(runtime, chapter)

        assert response.status_code == 200, response.text

        result = response.json()

        assert result["currentChapter"] == chapter
        assert result["revision"] == before.revision + 1

        assert {
            "type": "CHAPTER_CHANGED",
            "chapter": chapter,
        } in result["events"]

        actions = get_actions(runtime)

        # 현재 챕터가 아닌 조사 Action은 활성화하지 않는다.
        for action_id, _ in ALL_ACTIONS:
            candidate = ACTION_CANDIDATES[action_id]

            if candidate.chapter != chapter:
                assert actions[action_id] is False

        for action_id, eid in CHAPTER_ACTIONS[chapter]:
            collect_action(runtime, action_id, eid)

    state = get_state(runtime)

    assert set(state.evidence) == {
        eid for _, eid in ALL_ACTIONS
    }

    assert state.score == sum(
        PROPOSED_SCORES[eid]
        for _, eid in ALL_ACTIONS
    )

    assert state.score == 17

    assert set(state.unlocked_chapters) == {
        "CH00", "CH01", "CH02", "CH03",
    }

    # 이미 해금된 분기로 재방문한다.
    response = advance(runtime, first)

    assert response.status_code == 200, response.text

    revisited = get_state(runtime)

    assert revisited.current_chapter == first
    assert revisited.score == state.score
    assert revisited.evidence == state.evidence
    assert revisited.revision == state.revision + 1

    assert advance(runtime, second).status_code == 200

    # 최종 챕터의 조건이 충족되지 않았다.
    before = get_state(runtime)

    assert advance(runtime, "CH04").status_code == 409
    assert get_state(runtime) == before

    assert_game_consistency(runtime)


def test_day9_investigation_prerequisite_rollback(runtime):
    """챕터 및 선행 증거 조건 미충족 시 상태를 변경하지 않는다."""

    start_ch01(runtime)

    before = get_state(runtime)

    assert advance(runtime, "CH02").status_code == 409
    assert advance(runtime, "CH03").status_code == 409

    actions = get_actions(runtime)

    assert actions["inspect-e20-a"] is False

    assert investigate(
        runtime, "inspect-e20-a"
    ).status_code == 403

    assert investigate(
        runtime, "inspect-e12-a"
    ).status_code == 403

    assert get_state(runtime) == before

    collect_action(runtime, "inspect-e19-a", "E19")

    assert get_actions(runtime)["inspect-e20-a"] is True


def test_day9_investigation_duplicate_and_stale(runtime):
    """중복 획득 및 이전 상태 버전의 요청을 검증한다."""

    start_ch01(runtime)

    before = get_state(runtime)

    collect_action(runtime, "inspect-e11-a", "E11")

    after = get_state(runtime)

    repeated = investigate(runtime, "inspect-e11-a")

    assert repeated.status_code == 200
    assert repeated.json()["created"] is False
    assert repeated.json()["revision"] == after.revision

    stale = investigate(
        runtime,
        "inspect-e11-a",
        revision=before.revision,
    )

    assert stale.status_code == 409
    assert get_state(runtime) == after


def test_day9_investigation_session_restore(runtime):
    """HTTP 클라이언트 재생성 이후 게임 진행 정보를 복원한다."""

    app, client, repository, sid, _ = runtime

    prepare_branches(runtime)

    assert advance(runtime, "CH03").status_code == 200

    collect_action(runtime, "inspect-e21-a", "E21")

    before = get_state(runtime)

    with TestClient(app) as resumed:
        resumed.cookies.update(client.cookies)

        response = resumed.get(f"/api/games/{sid}")

        assert response.status_code == 200, response.text

        payload = response.json()

        assert payload["revision"] == before.revision
        assert payload["currentChapter"] == "CH03"
        assert payload["collection"]["score"] == before.score

        evidence = resumed.get(
            f"/api/games/{sid}/evidence"
        )

        assert evidence.status_code == 200

        collected = {
            item["evidenceId"]
            for item in evidence.json()["items"]
        }

        assert collected == set(before.evidence)

        locations = resumed.get(
            f"/api/games/{sid}/locations"
        )

        assert locations.status_code == 200
        assert locations.json()["revision"] == before.revision

    assert repository.load_state(sid) == before


def test_day9_investigation_npc_access(runtime):
    """현재 해금된 NPC만 선택할 수 있어야 한다."""

    _, client, repository, sid, _ = runtime

    start_ch01(runtime)

    before = get_state(runtime)
    game = get_game(runtime)

    assert game["unlockedCharacters"] == ["C01"]

    denied = client.post(
        f"/api/games/{sid}/characters/C02/select"
    )

    assert denied.status_code == 403
    assert get_state(runtime) == before

    allowed = client.post(
        f"/api/games/{sid}/characters/C01/select"
    )

    assert allowed.status_code == 200
    assert allowed.json()["activeCharacterId"] == "C01"

    assert_game_consistency(runtime)


def test_day9_investigation_approval_failure(runtime):
    """승인 서비스 오류 시 증거 획득을 차단한다."""

    _, _, _, _, settings = runtime

    start_ch01(runtime)

    before = get_state(runtime)

    settings["evidence_approved"] = False

    response = investigate(
        runtime, "inspect-e11-a"
    )

    assert response.status_code in (404, 503)
    assert get_state(runtime) == before
