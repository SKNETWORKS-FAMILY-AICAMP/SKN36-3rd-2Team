"""Issue #120 - Django 스토리 이벤트 클라이언트 및 공개 검증."""

import httpx
import pytest

from crimescene.api.django_content_client import (
    ApprovedStoryEvent,
    ContentServiceError,
    ContentServiceNotFoundError,
    DjangoContentClient,
)
from crimescene.api.story_event_gate import (
    select_releasable_story_event,
)
from crimescene.scenario.game_progress import create_initial_state
from crimescene.scenario.schemas.game_state import (
    EvidenceState,
    GamePhase,
)

TOKEN = "issue120-event-token-" + "A" * 48

EVENT = {
    "event_key": "EVT-CH00-001",
    "chapter": "CH00",
    "trigger_type": "EVIDENCE_COLLECTED",
    "required_evidence_ids": ["E01"],
    "title": "새로운 단서",
    "text": "기록이 발견되었습니다.",
}


def make_client(handler):
    return DjangoContentClient(
        base_url="http://127.0.0.1:8001",
        token=TOKEN,
        transport=httpx.MockTransport(handler),
    )


def make_state(*, collected=False, phase=GamePhase.INVESTIGATION):
    state = create_initial_state("story-event-test")

    return state.model_copy(
        update={
            "phase": phase,
            "evidence": ({"E01": EvidenceState(stage="found")} if collected else {}),
        }
    )


def test_approved_event_success():
    def handler(request):
        assert request.url.path == (
            "/api/content/internal/cases/CASE-001/events/EVT-CH00-001/"
        )
        assert request.headers["X-Content-Service-Token"] == TOKEN
        return httpx.Response(200, json=EVENT)

    with make_client(handler) as client:
        result = client.get_approved_story_event(
            "CASE-001",
            "EVT-CH00-001",
        )

    assert result.event_key == EVENT["event_key"]
    assert result.required_evidence_ids == ["E01"]


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (404, ContentServiceNotFoundError),
        (500, ContentServiceError),
    ],
)
def test_http_errors(status, error):
    def handler(request):
        return httpx.Response(status)

    with make_client(handler) as client, pytest.raises(error):
        client.get_approved_story_event(
            "CASE-001",
            "EVT-CH00-001",
        )


def test_wrong_event_id_rejected():
    def handler(request):
        return httpx.Response(
            200,
            json={**EVENT, "event_key": "EVT-CH00-002"},
        )

    with make_client(handler) as client, pytest.raises(ContentServiceError):
        client.get_approved_story_event(
            "CASE-001",
            "EVT-CH00-001",
        )


def test_private_fields_rejected():
    def handler(request):
        return httpx.Response(
            200,
            json={**EVENT, "internal_secret": "PRIVATE"},
        )

    with make_client(handler) as client, pytest.raises(ContentServiceError):
        client.get_approved_story_event(
            "CASE-001",
            "EVT-CH00-001",
        )


def test_duplicate_evidence_rejected():
    def handler(request):
        return httpx.Response(
            200,
            json={
                **EVENT,
                "required_evidence_ids": ["E01", "E01"],
            },
        )

    with make_client(handler) as client, pytest.raises(ContentServiceError):
        client.get_approved_story_event(
            "CASE-001",
            "EVT-CH00-001",
        )


def test_timeout_is_handled():
    def handler(request):
        raise httpx.ReadTimeout("timeout", request=request)

    with make_client(handler) as client, pytest.raises(ContentServiceError):
        client.get_approved_story_event(
            "CASE-001",
            "EVT-CH00-001",
        )


def test_invalid_event_id_blocks_request():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=EVENT)

    with make_client(handler) as client, pytest.raises(ValueError):
        client.get_approved_story_event(
            "CASE-001",
            "../invalid",
        )

    assert requests == []


def test_collected_evidence_unlocks_ch00_event():
    event = ApprovedStoryEvent(**EVENT)
    state = make_state(collected=True)

    assert select_releasable_story_event(event, state) == event


def test_missing_evidence_blocks_event():
    event = ApprovedStoryEvent(**EVENT)

    assert (
        select_releasable_story_event(
            event,
            make_state(collected=False),
        )
        is None
    )


def test_prologue_blocks_evidence_event():
    event = ApprovedStoryEvent(**EVENT)

    assert (
        select_releasable_story_event(
            event,
            make_state(
                collected=True,
                phase=GamePhase.PROLOGUE,
            ),
        )
        is None
    )


def test_locked_chapter_blocks_event():
    event = ApprovedStoryEvent(
        **{
            **EVENT,
            "event_key": "EVT-CH01-001",
            "chapter": "CH01",
        }
    )

    assert (
        select_releasable_story_event(
            event,
            make_state(collected=True),
        )
        is None
    )
