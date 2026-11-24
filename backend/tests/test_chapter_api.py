"""Issue #146 - 챕터 전환 API 통합 및 보안 테스트."""

from unittest.mock import Mock

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