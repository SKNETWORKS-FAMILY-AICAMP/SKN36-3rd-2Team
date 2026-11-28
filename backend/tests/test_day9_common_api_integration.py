"""이슈 #214 - 공통 기능 API 통합 검증."""

import pytest
from fastapi.testclient import TestClient

from crimescene.agents.contracts import AgentType
from crimescene.api.app import create_app
from crimescene.api.django_content_client import (
    ApprovedStoryEvent,
    ContentServiceError,
    ContentServiceNotFoundError,
)
from crimescene.api.story_event_conditions import (
    StoryEventConditions,
)
from crimescene.api.story_event_delivery_gate import (
    StoryEventBinding,
)
from crimescene.chat.npc_rag_service import NPCRAGResources
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.trigger.atomic_dialogue import (
    SQLiteCase001Repository,
)

from test_day9_investigation_progression import (
    runtime,
    get_state,
    get_game,
    start_ch01,
    collect_action,
    investigate,
    advance,
    assert_game_consistency,
)


EVENT_KEY = "EVT-CH01-901"
STORY_ID = "STORY_020"

EVENT_TITLE = "테스트 접수 기록 확인"
EVENT_TEXT = "테스트용으로 승인된 스토리 안내입니다."

NPC_IDS = [
    f"C{i:02d}" for i in range(1, 11)
]


def configure_agent_resources(runtime):
    """기존 조사 증거 카탈로그를 실제 MCP용 리소스로 구성한다."""

    app, _, _, _, _ = runtime

    rules = app.state.dialogue_resources.evidence_rules

    app.state.dialogue_resources = NPCRAGResources(
        personas={},
        qdrant_client=None,
        neo4j_driver=None,
        embedder=None,
        encoder=None,
        trusted_records=(),
        documents=(),
        npc_cards=(),
        registry=(),
        trusted_edges=(),
        evidence_rules=rules,
        evaluator=PolicyEvaluator({}),
        content_version="case001_1120",
    )


def configure_story_event(runtime, monkeypatch):
    """테스트용 승인 이벤트 및 실제 서버 평가 조건을 구성한다."""

    app, _, _, _, _ = runtime

    event = ApprovedStoryEvent(
        event_key=EVENT_KEY,
        chapter="CH01",
        trigger_type="EVIDENCE_COLLECTED",
        required_evidence_ids=["E19"],
        title=EVENT_TITLE,
        text=EVENT_TEXT,
    )

    app.state.story_event_bindings = {
        EVENT_KEY: StoryEventBinding(
            source_story_id=STORY_ID,
            event_key=EVENT_KEY,
            chapter="CH01",
        ),
    }

    app.state.story_event_conditions = {
        STORY_ID: StoryEventConditions(
            story_id=STORY_ID,
            chapter="CH01",
            all_evidence=frozenset({"E19"}),
            required_flags=frozenset({
                "ACT_RECEPTION_RECORD_INSPECTED",
            }),
        ),
    }

    approval = {"mode": "approved"}

    def fetch(case_id, event_key):
        assert case_id == "CASE-001"
        assert event_key == EVENT_KEY

        if approval["mode"] == "unpublished":
            raise ContentServiceNotFoundError(
                "Test event is not published"
            )

        if approval["mode"] == "unavailable":
            raise ContentServiceError(
                "Test content service unavailable"
            )

        return event

    monkeypatch.setattr(
        app.state.django_content_client,
        "get_approved_story_event",
        fetch,
    )

    return approval


def hint(runtime, level, revision=None):
    _, client, _, sid, _ = runtime

    return client.post(
        f"/api/games/{sid}/agents/hint",
        json={
            "level": level,
            "expectedRevision": (
                get_state(runtime).revision
                if revision is None
                else revision
            ),
        },
    )


@pytest.mark.parametrize("level", [1, 2, 3])
def test_day9_hint_mcp_integration(runtime, level):
    """실제 HTTP와 MCP를 통한 단계별 힌트를 검증한다."""

    configure_agent_resources(runtime)

    _, _, repository, sid, _ = runtime

    start_ch01(runtime)

    collect_action(
        runtime,
        "inspect-e11-a",
        "E11",
    )

    collect_action(
        runtime,
        "inspect-e19-a",
        "E19",
    )

    before = get_state(runtime)
    selection = repository.load_selection(sid)

    # 같은 Revision에서 반복 요청해도 상태가 변경되지 않는다.
    for _ in range(2):
        response = hint(runtime, level)

        assert response.status_code == 200, response.text

        payload = response.json()

        assert payload["agentType"] == AgentType.HINT.value
        assert payload["level"] == level
        assert payload["status"] == "READY"
        assert payload["chapter"] == "CH01"
        assert payload["collectedCount"] == 2
        assert payload["revision"] == before.revision
        assert payload["text"].strip()

        assert set(payload["sourceIds"]).issubset(
            before.evidence
        )

        assert response.headers["cache-control"] == "no-store"

        if level == 1:
            assert payload["sourceIds"] == []

        elif level == 2:
            assert set(payload["sourceIds"]) == {
                "E11", "E19"
            }

        else:
            assert len(payload["sourceIds"]) == 1
            assert (
                payload["suggestedCharacterId"]
                in before.unlocked_characters
            )

        assert "E30" not in payload["text"]
        assert "E28" not in payload["text"]

        assert get_state(runtime) == before
        assert repository.load_selection(sid) == selection

    assert_game_consistency(runtime)


def test_day9_hint_empty_evidence(runtime):
    """수집 증거가 없어도 공개 정보만 안내한다."""

    configure_agent_resources(runtime)
    start_ch01(runtime)

    before = get_state(runtime)

    for level in (2, 3):
        response = hint(runtime, level)

        assert response.status_code == 200, response.text

        payload = response.json()

        assert payload["status"] == "NO_EVIDENCE"
        assert payload["sourceIds"] == []
        assert payload["collectedCount"] == 0
        assert payload["revision"] == before.revision

        if payload["suggestedCharacterId"] is not None:
            assert (
                payload["suggestedCharacterId"]
                in before.unlocked_characters
            )

        assert get_state(runtime) == before


def test_day9_hint_invalid_requests(runtime):
    """프롤로그, 이전 Revision 및 비정상 요청을 차단한다."""

    configure_agent_resources(runtime)

    app, _, _, sid, _ = runtime

    before = get_state(runtime)

    # 프롤로그에서는 힌트 실행이 허용되지 않는다.
    response = hint(runtime, 1)

    assert response.status_code == 409
    assert get_state(runtime) == before

    start_ch01(runtime)

    before = get_state(runtime)

    stale = hint(
        runtime,
        1,
        revision=before.revision - 1,
    )

    assert stale.status_code == 409

    for invalid_level in (0, 4, -1, True, "3"):
        response = hint(runtime, invalid_level)

        assert response.status_code == 422

    # 다른 플레이어의 세션으로 힌트를 요청할 수 없다.
    with TestClient(app) as stranger:
        created = stranger.post("/api/games")

        assert created.status_code == 201

        denied = stranger.post(
            f"/api/games/{sid}/agents/hint",
            json={
                "level": 1,
                "expectedRevision": before.revision,
            },
        )

        assert denied.status_code == 404

    assert get_state(runtime) == before


def test_day9_story_event_and_session_restore(
    runtime,
    monkeypatch,
    tmp_path,
):
    """증거 획득부터 이벤트 확인 및 저장 상태 복원까지 검증한다."""

    app, client, repository, sid, _ = runtime

    configure_agent_resources(runtime)

    configure_story_event(
        runtime,
        monkeypatch,
    )

    completed = client.post(
        f"/api/games/{sid}/prologue/complete"
    )

    assert completed.status_code == 200

    chapter = advance(runtime, "CH01")

    assert chapter.status_code == 200, chapter.text

    game = chapter.json()

    assert game["unlockedCharacters"] == NPC_IDS

    assert {
        "type": "CHAPTER_CHANGED",
        "chapter": "CH01",
    } in game["events"]

    assert {
        "type": "GAME_PROGRESS_UPDATED",
    } in game["events"]

    unlocked_events = [
        event["characterId"]
        for event in game["events"]
        if event["type"] == "NPC_UNLOCKED"
    ]

    assert unlocked_events == NPC_IDS[1:]

    pending_url = (
        f"/api/games/{sid}/story-events/pending"
    )

    detail_url = (
        f"/api/games/{sid}/story-events/{EVENT_KEY}"
    )

    # 선행 증거를 획득하기 전에는 이벤트가 공개되지 않는다.
    assert client.get(pending_url).json() == {
        "items": []
    }

    assert client.get(detail_url).status_code == 404

    assert client.post(
        detail_url + "/ack"
    ).status_code == 404

    before = get_state(runtime)

    # 실제 현장 조사 요청이 이벤트 조건을 충족시킨다.
    acquired = investigate(runtime, "inspect-e19-a")

    assert acquired.status_code == 200, acquired.text

    result = acquired.json()

    assert result["created"] is True
    assert result["evidenceId"] == "E19"

    queued = get_state(runtime)

    assert "E19" in queued.evidence
    assert STORY_ID in queued.queued_story_events
    assert STORY_ID not in queued.acknowledged_story_events

    # 증거 획득과 이벤트 큐 저장은 한 번의 상태 변경으로 처리된다.
    assert queued.revision == before.revision + 1

    assert result["revision"] == queued.revision

    # 현장 조사 중복 요청은 이벤트도 중복 생성하지 않는다.
    duplicate = investigate(runtime, "inspect-e19-a")

    assert duplicate.status_code == 200
    assert duplicate.json()["created"] is False
    assert get_state(runtime) == queued

    expected_event = {
        "eventKey": EVENT_KEY,
        "chapter": "CH01",
        "title": EVENT_TITLE,
        "text": EVENT_TEXT,
    }

    response = client.get(pending_url)

    assert response.status_code == 200
    assert response.json() == {
        "items": [expected_event]
    }

    assert client.get(detail_url).json() == expected_event
    assert get_state(runtime) == queued

    # 공개된 NPC를 선택한 상태도 함께 복원되어야 한다.
    selected = client.post(
        f"/api/games/{sid}/characters/C07/select"
    )

    assert selected.status_code == 200

    before_restore = get_state(runtime)

    # 동일한 SQLite 파일을 사용하는 새 저장소 객체와
    # 새 FastAPI 애플리케이션을 생성한다.
    restored_repository = SQLiteCase001Repository(
        tmp_path / "day9-progression.sqlite3"
    )

    restored_app = create_app(
        restored_repository,
        session_secret="day9-progression-" + "x" * 40,
    )

    # 실제 배포에서는 런타임 초기화가 담당하는 설정이다.
    for attribute in (
        "content_version",
        "dialogue_resources",
        "django_content_client",
        "chapter_unlock_rules",
        "story_event_bindings",
        "story_event_conditions",
    ):
        setattr(
            restored_app.state,
            attribute,
            getattr(app.state, attribute),
        )

    with TestClient(restored_app) as resumed:
        resumed.cookies.update(client.cookies)

        restored = resumed.get(
            f"/api/games/{sid}"
        )

        assert restored.status_code == 200, restored.text

        payload = restored.json()

        assert payload["sessionId"] == sid
        assert payload["currentChapter"] == "CH01"
        assert payload["unlockedCharacters"] == NPC_IDS
        assert payload["activeCharacterId"] == "C07"

        assert payload["revision"] == before_restore.revision
        assert payload["collection"]["score"] == before_restore.score

        # GameResponse.events는 영속 알림 목록이 아니다.
        assert payload["events"] == []

        assert (
            restored_repository.load_state(sid)
            == before_restore
        )

        evidence = resumed.get(
            f"/api/games/{sid}/evidence"
        )

        assert evidence.status_code == 200

        assert {
            item["evidenceId"]
            for item in evidence.json()["items"]
        } == {"E19"}

        # ACK 이전 이벤트는 재접속 이후에도 유지된다.
        pending = resumed.get(pending_url)

        assert pending.status_code == 200
        assert pending.json() == {
            "items": [expected_event]
        }

        first_ack = resumed.post(
            detail_url + "/ack"
        )

        assert first_ack.status_code == 200

        ack = first_ack.json()

        assert ack["acknowledged"] is True
        assert ack["created"] is True

        assert ack["revision"] == (
            before_restore.revision + 1
        )

        saved = restored_repository.load_state(sid)

        assert saved.acknowledged_story_events == [
            STORY_ID
        ]

        assert saved.evidence == before_restore.evidence
        assert saved.score == before_restore.score

        assert restored_repository.load_selection(sid) == (
            "C07",
            saved.revision,
        )

        # 중복 ACK는 상태 및 Revision을 변경하지 않는다.
        retry = resumed.post(
            detail_url + "/ack"
        )

        assert retry.status_code == 200
        assert retry.json()["created"] is False
        assert retry.json()["revision"] == saved.revision

        assert restored_repository.load_state(sid) == saved

        assert resumed.get(pending_url).json() == {
            "items": []
        }

        assert resumed.get(detail_url).status_code == 404

    # 기존 저장소 객체에서도 변경이 확인되어야 한다.
    assert repository.load_state(sid) == saved

    # 재접속 이후에도 확인한 이벤트는 다시 표시하지 않는다.
    with TestClient(restored_app) as reconnected:
        reconnected.cookies.update(client.cookies)

        assert reconnected.get(pending_url).json() == {
            "items": []
        }


@pytest.mark.parametrize(
    ("mode", "expected_status"),
    [
        ("unpublished", 200),
        ("unavailable", 503),
    ],
)
def test_day9_story_approval_failure(
    runtime,
    monkeypatch,
    mode,
    expected_status,
):
    """미승인 이벤트 노출과 승인 장애 시 부분 저장을 방지한다."""

    _, client, _, sid, _ = runtime

    approval = configure_story_event(
        runtime,
        monkeypatch,
    )

    start_ch01(runtime)

    approval["mode"] = mode

    before = get_state(runtime)

    response = investigate(
        runtime,
        "inspect-e19-a",
    )

    assert response.status_code == expected_status, response.text

    after = get_state(runtime)

    if mode == "unpublished":
        # 일반 미게시 이벤트는 숨기되 정상 증거 획득은 유지한다.
        assert "E19" in after.evidence

        assert after.revision == before.revision + 1

    else:
        # 승인 서비스 장애에서는 증거 및 이벤트 저장을 롤백한다.
        assert after == before

    assert STORY_ID not in after.queued_story_events
    assert STORY_ID not in after.acknowledged_story_events

    pending = client.get(
        f"/api/games/{sid}/story-events/pending"
    )

    assert pending.status_code == 200
    assert pending.json() == {
        "items": []
    }

    assert_game_consistency(runtime)
