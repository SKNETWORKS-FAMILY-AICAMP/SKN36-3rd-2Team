"""Issue #146 - 챕터 전환 API 통합 및 보안 테스트."""

from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient

from crimescene.api.app import create_app
from crimescene.api.django_content_client import (
    ApprovedStoryEvent,
    ContentServiceError,
    DjangoContentClient,
)
from crimescene.api.story_event_conditions import StoryEventConditions
from crimescene.api.story_event_delivery_gate import StoryEventBinding
from crimescene.scenario.chapter_progress import ChapterUnlockRule
from crimescene.scenario.schemas.game_state import (
    EvidenceState,
    GameState,
)
from crimescene.scenario.story_context import StoryContextService
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository


@pytest.fixture
def runtime(tmp_path):
    repository = SQLiteCase001Repository(
        tmp_path / "chapter-api.sqlite3"
    )

    app = create_app(
        repository,
        session_secret="chapter-api-test-" + "x" * 40,
    )

    # 테스트 전용 규칙이며 실제 스토리 해금 조건은 아닙니다.
    app.state.chapter_unlock_rules = {
        f"CH0{i}": ChapterUnlockRule(
            target_chapter=f"CH0{i}",
            required_evidence=frozenset({"E01"}),
            required_flags=frozenset({"TEST_READY"}),
            required_presentations=frozenset({"C01:E01"}),
        )
        for i in range(1, 5)
    }

    with TestClient(app) as client:
        response = client.post("/api/games")
        assert response.status_code == 201

        session_id = response.json()["sessionId"]

        response = client.post(
            f"/api/games/{session_id}/prologue/complete"
        )
        assert response.status_code == 200

        current = repository.load_state(session_id)

        ready = GameState.model_validate(
            {
                **current.model_dump(mode="python"),
                "evidence": {
                    "E01": EvidenceState(stage="found"),
                },
                "flags": ["TEST_READY"],
                "presented": {"C01": ["E01"]},
                "revision": current.revision + 1,
            }
        )

        repository.commit_state(
            expected_state=current,
            updated_state=ready,
        )

        yield app, client, repository, session_id


def advance_url(session_id):
    return f"/api/games/{session_id}/chapter/advance"


def test_sequential_chapter_progress(runtime):
    _, client, repository, session_id = runtime

    for index in range(1, 5):
        before = repository.load_state(session_id)
        target = f"CH0{index}"

        response = client.post(
            advance_url(session_id),
            json={"expectedRevision": before.revision},
        )

        assert response.status_code == 200

        result = response.json()

        assert result["currentChapter"] == target
        assert result["revision"] == before.revision + 1

        assert result["unlockedChapters"] == [
            f"CH0{i}" for i in range(index + 1)
        ]

        persisted = repository.load_state(session_id)

        assert persisted.current_chapter == target
        assert persisted.revision == result["revision"]

        # NPC 선택 정보의 revision도 함께 갱신돼야 합니다.
        selection = repository.load_selection(session_id)

        assert selection == ("C01", persisted.revision)

        context = StoryContextService(repository).load(
            session_id,
            expected_revision=persisted.revision,
        )

        assert context.current_chapter == target

        resumed = client.get(f"/api/games/{session_id}")

        assert resumed.status_code == 200
        assert resumed.json()["currentChapter"] == target

    final = repository.load_state(session_id)

    # CH04 이후 추가 전환을 차단합니다.
    response = client.post(
        advance_url(session_id),
        json={"expectedRevision": final.revision},
    )

    assert response.status_code == 409
    assert repository.load_state(session_id) == final


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("evidence", {}),
        ("flags", []),
        ("presented", {}),
    ],
)
def test_missing_unlock_requirements(
    runtime,
    field,
    value,
):
    _, client, repository, session_id = runtime

    current = repository.load_state(session_id)

    blocked = GameState.model_validate(
        {
            **current.model_dump(mode="python"),
            field: value,
            "revision": current.revision + 1,
        }
    )

    repository.commit_state(
        expected_state=current,
        updated_state=blocked,
    )

    response = client.post(
        advance_url(session_id),
        json={"expectedRevision": blocked.revision},
    )

    assert response.status_code == 409
    assert repository.load_state(session_id) == blocked


def test_duplicate_request_is_rejected(runtime):
    _, client, repository, session_id = runtime

    before = repository.load_state(session_id)
    payload = {"expectedRevision": before.revision}

    first = client.post(
        advance_url(session_id),
        json=payload,
    )

    assert first.status_code == 200

    committed = repository.load_state(session_id)

    second = client.post(
        advance_url(session_id),
        json=payload,
    )

    assert second.status_code == 409
    assert repository.load_state(session_id) == committed


def test_missing_server_rule_fails_closed(runtime):
    app, client, repository, session_id = runtime

    app.state.chapter_unlock_rules = {}

    before = repository.load_state(session_id)

    response = client.post(
        advance_url(session_id),
        json={"expectedRevision": before.revision},
    )

    assert response.status_code == 503
    assert repository.load_state(session_id) == before


def test_wrong_target_rule_is_rejected(runtime):
    app, client, repository, session_id = runtime

    app.state.chapter_unlock_rules = {
        "CH01": ChapterUnlockRule(
            target_chapter="CH03",
            required_evidence=frozenset({"E01"}),
        )
    }

    before = repository.load_state(session_id)

    response = client.post(
        advance_url(session_id),
        json={"expectedRevision": before.revision},
    )

    assert response.status_code == 503
    assert repository.load_state(session_id) == before


@pytest.mark.parametrize(
    "extra_fields",
    [
        {"targetChapter": "CH04"},
        {"requiredEvidence": []},
        {"unlockedChapters": ["CH00", "CH04"]},
    ],
)
def test_client_cannot_inject_chapter_rules(
    runtime,
    extra_fields,
):
    _, client, repository, session_id = runtime

    before = repository.load_state(session_id)

    response = client.post(
        advance_url(session_id),
        json={
            "expectedRevision": before.revision,
            **extra_fields,
        },
    )

    assert response.status_code == 422
    assert repository.load_state(session_id) == before


def test_other_player_cannot_advance_chapter(runtime):
    app, _, repository, session_id = runtime

    before = repository.load_state(session_id)

    with TestClient(app) as stranger:
        response = stranger.post(
            advance_url(session_id),
            json={"expectedRevision": before.revision},
        )

    assert response.status_code == 404
    assert repository.load_state(session_id) == before


@pytest.mark.parametrize(
    "revision",
    [-1, True, "2", None],
)
def test_invalid_revision_is_rejected(runtime, revision):
    _, client, repository, session_id = runtime

    before = repository.load_state(session_id)

    response = client.post(
        advance_url(session_id),
        json={"expectedRevision": revision},
    )

    assert response.status_code == 422
    assert repository.load_state(session_id) == before


@pytest.fixture
def chapter_event_runtime(runtime):
    app, client, repository, session_id = runtime

    event_key = "EVT-CH01-001"
    story_id = "STORY_001"

    app.state.story_event_bindings = {
        event_key: StoryEventBinding(
            source_story_id=story_id,
            event_key=event_key,
            chapter="CH01",
        )
    }

    app.state.story_event_conditions = {
        story_id: StoryEventConditions(
            story_id=story_id,
            chapter="CH01",
            all_evidence=frozenset({"E01"}),
            required_flags=frozenset({"TEST_READY"}),
        )
    }

    django_client = Mock(spec=DjangoContentClient)

    django_client.get_approved_story_event.return_value = (
        ApprovedStoryEvent(
            event_key=event_key,
            chapter="CH01",
            trigger_type="EVIDENCE_COLLECTED",
            required_evidence_ids=["E01"],
            title="Chapter test event",
            text="Approved test content",
        )
    )

    app.state.django_content_client = django_client

    return client, repository, session_id, django_client


def test_chapter_and_story_event_commit_atomically(
    chapter_event_runtime,
):
    client, repository, session_id, django_client = (
        chapter_event_runtime
    )

    before = repository.load_state(session_id)

    response = client.post(
        advance_url(session_id),
        json={"expectedRevision": before.revision},
    )

    assert response.status_code == 200, response.text

    saved = repository.load_state(session_id)

    assert saved.current_chapter == "CH01"
    assert saved.unlocked_chapters == ["CH00", "CH01"]
    assert saved.queued_story_events == ["STORY_001"]
    assert saved.revision == before.revision + 1

    assert repository.load_selection(session_id) == (
        "C01",
        saved.revision,
    )

    context = StoryContextService(repository).load(
        session_id,
        expected_revision=saved.revision,
    )

    assert context.current_chapter == "CH01"

    django_client.get_approved_story_event.assert_called_once_with(
        "CASE-001",
        "EVT-CH01-001",
    )


def test_chapter_event_django_failure_preserves_state(
    chapter_event_runtime,
):
    client, repository, session_id, django_client = (
        chapter_event_runtime
    )

    before = repository.load_state(session_id)

    django_client.get_approved_story_event.side_effect = (
        ContentServiceError("Django unavailable")
    )

    response = client.post(
        advance_url(session_id),
        json={"expectedRevision": before.revision},
    )

    assert response.status_code == 503, response.text
    assert repository.load_state(session_id) == before

    assert repository.load_selection(session_id) == (
        "C01",
        before.revision,
    )


def test_stale_chapter_request_does_not_queue_event(
    chapter_event_runtime,
):
    client, repository, session_id, django_client = (
        chapter_event_runtime
    )

    before = repository.load_state(session_id)

    response = client.post(
        advance_url(session_id),
        json={"expectedRevision": before.revision - 1},
    )

    assert response.status_code == 409

    assert repository.load_state(session_id) == before

    django_client.get_approved_story_event.assert_not_called()


def test_chapter_event_is_not_duplicated(
    chapter_event_runtime,
):
    client, repository, session_id, django_client = (
        chapter_event_runtime
    )

    before = repository.load_state(session_id)

    first = client.post(
        advance_url(session_id),
        json={"expectedRevision": before.revision},
    )

    assert first.status_code == 200, first.text

    current = repository.load_state(session_id)

    second = client.post(
        advance_url(session_id),
        json={"expectedRevision": current.revision},
    )

    assert second.status_code == 200, second.text

    saved = repository.load_state(session_id)

    assert saved.current_chapter == "CH02"
    assert saved.queued_story_events == ["STORY_001"]

    django_client.get_approved_story_event.assert_called_once()


@pytest.fixture
def day5_chapter_runtime(runtime):
    app, client, repository, session_id = runtime

    token = "day5-integration-token-" + "x" * 40
    bindings = {}
    conditions = {}
    responses = {}
    requests = []

    prefix = "/api/content/internal/cases/CASE-001"

    # 테스트용 CH01, CH02 콘텐츠를 구성합니다.
    for index in (1, 2):
        chapter = f"CH0{index}"
        story_id = f"STORY_{index:03d}"
        event_key = f"EVT-{chapter}-001"
        scene_id = f"SC-{index:04d}"

        bindings[event_key] = StoryEventBinding(
            source_story_id=story_id,
            event_key=event_key,
            chapter=chapter,
        )

        conditions[story_id] = StoryEventConditions(
            story_id=story_id,
            chapter=chapter,
            all_evidence=frozenset({"E01"}),
            required_flags=frozenset({"TEST_READY"}),
        )

        responses[f"{prefix}/events/{event_key}/"] = {
            "event_key": event_key,
            "chapter": chapter,
            "trigger_type": "EVIDENCE_COLLECTED",
            "required_evidence_ids": ["E01"],
            "title": f"Test event {chapter}",
            "text": f"APPROVED_EVENT_{chapter}",
        }

        responses[f"{prefix}/scenes/{scene_id}/"] = {
            "scene_id": scene_id,
            "chapter": chapter,
            "title": f"Test scene {chapter}",
            "scene_text": f"APPROVED_SCENE_{chapter}",
        }

    def handler(request):
        assert request.method == "GET"
        assert (
            request.headers["X-Content-Service-Token"]
            == token
        )

        path = request.url.path
        requests.append(path)

        if path not in responses:
            return httpx.Response(
                404,
                json={"detail": "Not approved"},
            )

        return httpx.Response(
            200,
            json=responses[path],
        )

    app.state.story_event_bindings = bindings
    app.state.story_event_conditions = conditions

    with DjangoContentClient(
        base_url="http://127.0.0.1:8001",
        token=token,
        transport=httpx.MockTransport(handler),
    ) as django_client:
        app.state.django_content_client = django_client

        yield (
            client,
            repository,
            session_id,
            responses,
            requests,
        )


def test_day5_chapter_scene_event_lifecycle(
    day5_chapter_runtime,
    tmp_path,
):
    client, repository, session_id, _, requests = (
        day5_chapter_runtime
    )

    base = f"/api/games/{session_id}"
    service = StoryContextService(repository)

    before = repository.load_state(session_id)

    # CH00에서는 미래 장면과 이벤트를 공개하지 않습니다.
    locked = client.get(
        f"{base}/content/scenes/SC-0001"
    )

    assert locked.status_code == 404
    assert "APPROVED_SCENE_CH01" not in locked.text

    pending = client.get(
        f"{base}/story-events/pending"
    )

    assert pending.status_code == 200
    assert pending.json() == {"items": []}
    assert repository.load_state(session_id) == before

    for index in (1, 2):
        chapter = f"CH0{index}"
        story_id = f"STORY_{index:03d}"
        event_key = f"EVT-{chapter}-001"
        scene_id = f"SC-{index:04d}"

        current = repository.load_state(session_id)

        # 실제 Chapter API를 통해 진행합니다.
        advanced = client.post(
            advance_url(session_id),
            json={
                "expectedRevision": current.revision,
            },
        )

        assert advanced.status_code == 200, advanced.text

        saved = repository.load_state(session_id)

        assert saved.current_chapter == chapter
        assert saved.revision == current.revision + 1
        assert story_id in saved.queued_story_events

        context = service.load(
            session_id,
            expected_revision=saved.revision,
        )

        assert context.current_chapter == chapter
        assert context.collected_evidence_ids == ("E01",)
        assert context.get_presented_evidence("C01") == (
            "E01",
        )

        # 현재 챕터의 승인된 Scene을 공개합니다.
        scene = client.get(
            f"{base}/content/scenes/{scene_id}"
        )

        assert scene.status_code == 200
        assert scene.json()["chapter"] == chapter
        assert (
            scene.json()["sceneText"]
            == f"APPROVED_SCENE_{chapter}"
        )

        pending = client.get(
            f"{base}/story-events/pending"
        )

        assert pending.status_code == 200

        assert [
            item["eventKey"]
            for item in pending.json()["items"]
        ] == [event_key]

        # 현재 챕터 이외의 콘텐츠 접근 차단
        other_index = 2 if index == 1 else 1
        other_chapter = f"CH0{other_index}"
        other_scene = f"SC-{other_index:04d}"
        other_event = f"EVT-{other_chapter}-001"

        assert client.get(
            f"{base}/content/scenes/{other_scene}"
        ).status_code == 404

        assert client.get(
            f"{base}/story-events/{other_event}"
        ).status_code == 404

        # 읽기 전용 API는 GameState를 수정하지 않습니다.
        assert repository.load_state(session_id) == saved

        detail = client.get(
            f"{base}/story-events/{event_key}"
        )

        assert detail.status_code == 200
        assert detail.json()["text"] == (
            f"APPROVED_EVENT_{chapter}"
        )

        # 이벤트 확인 및 멱등성 검증
        ack_url = f"{base}/story-events/{event_key}/ack"

        first = client.post(ack_url)

        assert first.status_code == 200
        assert first.json()["created"] is True

        second = client.post(ack_url)

        assert second.status_code == 200
        assert second.json()["created"] is False
        assert second.json()["revision"] == (
            first.json()["revision"]
        )

        acknowledged = repository.load_state(session_id)

        assert acknowledged.revision == saved.revision + 1
        assert story_id in (
            acknowledged.acknowledged_story_events
        )

        assert client.get(
            f"{base}/story-events/pending"
        ).json() == {"items": []}

    final = repository.load_state(session_id)

    assert final.current_chapter == "CH02"

    assert final.queued_story_events == [
        "STORY_001",
        "STORY_002",
    ]

    assert final.acknowledged_story_events == [
        "STORY_001",
        "STORY_002",
    ]

    # 저장소를 다시 열어 진행 상태의 영속성을 검증합니다.
    reopened = SQLiteCase001Repository(
        tmp_path / "chapter-api.sqlite3"
    )

    assert reopened.load_state(session_id) == final

    assert reopened.load_selection(session_id) == (
        "C01",
        final.revision,
    )

    resumed = client.get(base)

    assert resumed.status_code == 200
    assert resumed.json()["currentChapter"] == "CH02"
    assert resumed.json()["revision"] == final.revision

    # 실제 DjangoContentClient HTTP 경로 호출 확인
    assert any("/scenes/" in path for path in requests)
    assert any("/events/" in path for path in requests)


def test_day5_unapproved_content_is_not_exposed(
    day5_chapter_runtime,
):
    client, repository, session_id, responses, _ = (
        day5_chapter_runtime
    )

    base = f"/api/games/{session_id}"
    prefix = "/api/content/internal/cases/CASE-001"

    # Django에서 미승인 콘텐츠에 404를 반환하는 상황
    responses.pop(
        f"{prefix}/events/EVT-CH01-001/"
    )

    responses.pop(
        f"{prefix}/scenes/SC-0001/"
    )

    before = repository.load_state(session_id)

    advanced = client.post(
        advance_url(session_id),
        json={"expectedRevision": before.revision},
    )

    # 미승인 이벤트는 제외하되 정상 챕터 전환은 허용합니다.
    assert advanced.status_code == 200, advanced.text

    saved = repository.load_state(session_id)

    assert saved.current_chapter == "CH01"
    assert saved.queued_story_events == []
    assert saved.acknowledged_story_events == []

    assert client.get(
        f"{base}/content/scenes/SC-0001"
    ).status_code == 404

    pending = client.get(
        f"{base}/story-events/pending"
    )

    assert pending.status_code == 200
    assert pending.json() == {"items": []}

    event_url = f"{base}/story-events/EVT-CH01-001"

    assert client.get(event_url).status_code == 404
    assert client.post(
        event_url + "/ack"
    ).status_code == 404

    assert repository.load_state(session_id) == saved