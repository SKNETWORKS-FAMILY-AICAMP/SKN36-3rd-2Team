
"""Issue #131 - NPC Agent와 SQLite 원자적 저장 통합 테스트."""

import sqlite3
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

import crimescene.trigger.atomic_dialogue as atomic_module
from crimescene.agents.contracts import AgentContext
from crimescene.api.app import create_app
from crimescene.api.django_content_client import (
    ApprovedStoryEvent,
    ContentServiceError,
    DjangoContentClient,
)
from crimescene.api.story_event_conditions import StoryEventConditions
from crimescene.api.story_event_delivery_gate import StoryEventBinding
from crimescene.chat.npc_chat_runtime import NPCChatTurn
from crimescene.chat.npc_rag_service import NPCRAGResources
from crimescene.retriever.npc_output_guard import NPCGroundedReply
from crimescene.retriever.npc_response_gate import FALLBACK_REPLY
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.scenario.schemas.game_state import GameState
from crimescene.scenario.story_context import StoryContextService
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository
from crimescene.trigger.case001_dialogue import Case001DialogueResult
from crimescene.trigger.npc_trigger import (
    NPCTriggerRule,
    apply_npc_triggers,
)


def make_app(tmp_path):
    repository = SQLiteCase001Repository(tmp_path / "game.sqlite3")
    app = create_app(
        repository,
        session_secret="test-secret-" + "a" * 32,
    )

    resources = Mock(spec=NPCRAGResources)
    resources.npc_cards = []
    resources.evidence_rules = {}

    app.state.dialogue_resources = resources
    app.state.dialogue_policies = {}
    app.state.dialogue_triggers = ()
    app.state.dialogue_flag_config = None

    return app, repository, resources


def start_game(client):
    created = client.post("/api/games")
    assert created.status_code == 201

    session_id = created.json()["sessionId"]

    completed = client.post(
        f"/api/games/{session_id}/prologue/complete"
    )
    assert completed.status_code == 200

    return session_id


def test_npc_agent_commits_exactly_once(tmp_path, monkeypatch):
    """Adapter가 실제 원자적 엔진을 통해 대화 한 건만 저장합니다."""
    app, repository, expected_resources = make_app(tmp_path)
    calls = []

    def fake_dialogue(
        question,
        *,
        state,
        session_store,
        resources,
        policies,
        trigger_rules,
        presented_evidence_id,
    ):
        calls.append(question)
        assert resources is expected_resources
        assert presented_evidence_id is None

        # 실제 SQLite에는 아직 기록되지 않았어야 합니다.
        assert repository.load_history(state.session_id, "C01") == ()

        reply = NPCGroundedReply(
            text=FALLBACK_REPLY,
            source_ids=(),
            grounded=False,
        )

        exchange = session_store.append_verified_exchange(
            state,
            "C01",
            user_message=question,
            reply=reply,
        )

        # 원자적 엔진이 커밋하기 전까지 DB 변경이 없어야 합니다.
        assert repository.load_history(state.session_id, "C01") == ()

        return Case001DialogueResult(
            turn=NPCChatTurn(
                character_id="C01",
                reply=reply,
                exchange=exchange,
                display_text=FALLBACK_REPLY,
            ),
            state=state,
            presentation_created=False,
            trigger_ids=(),
            disclosed_card_ids=(),
        )

    # 원자적 저장 함수가 아닌 내부 대화 생성만 대체합니다.
    monkeypatch.setattr(
        atomic_module,
        "run_case001_npc_dialogue",
        fake_dialogue,
    )

    with TestClient(app) as client:
        session_id = start_game(client)

        response = client.post(
            f"/api/games/{session_id}/chat",
            json={"question": "안녕하세요."},
        )

    assert response.status_code == 200, response.text

    body = response.json()
    assert body["characterId"] == "C01"
    assert body["display_text"] == FALLBACK_REPLY
    assert body["game"]["revision"] == 2
    assert body["game"]["events"] == [
        {"type": "NPC_REPLIED", "characterId": "C01"}
    ]

    # 내부 대화 생성 및 SQLite 저장 모두 정확히 한 번
    assert calls == ["안녕하세요."]
    assert len(repository.load_history(session_id, "C01")) == 1
    assert repository.load_state(session_id).revision == 2
    assert repository.load_selection(session_id) == ("C01", 2)


def test_npc_agent_failure_does_not_commit(tmp_path, monkeypatch):
    """대화 생성 중 예외가 발생하면 게임 상태를 변경하지 않습니다."""
    app, repository, _ = make_app(tmp_path)

    def failing_dialogue(
        question,
        *,
        state,
        session_store,
        resources,
        policies,
        trigger_rules,
        presented_evidence_id,
    ):
        reply = NPCGroundedReply(
            text=FALLBACK_REPLY,
            source_ids=(),
            grounded=False,
        )

        # 임시 저장 후 강제로 실패시킵니다.
        session_store.append_verified_exchange(
            state,
            "C01",
            user_message=question,
            reply=reply,
        )

        raise RuntimeError("Injected dialogue failure")

    monkeypatch.setattr(
        atomic_module,
        "run_case001_npc_dialogue",
        failing_dialogue,
    )

    with TestClient(
        app,
        raise_server_exceptions=False,
    ) as client:
        session_id = start_game(client)

        response = client.post(
            f"/api/games/{session_id}/chat",
            json={"question": "안녕하세요."},
        )

    assert response.status_code == 500

    # 예외가 발생했으므로 실제 SQLite에는 변경이 없어야 합니다.
    assert repository.load_history(session_id, "C01") == ()
    assert repository.load_state(session_id).revision == 1
    assert repository.load_selection(session_id) == ("C01", 1)

EVENT_KEY = "EVT-CH00-001"
STORY_ID = "STORY_001"
TRIGGER_FLAG = "TEST_EVENT_READY"


@pytest.fixture
def story_event_runtime(tmp_path, monkeypatch):
    app, repository, _ = make_app(tmp_path)

    app.state.story_event_bindings = {
        EVENT_KEY: StoryEventBinding(
            source_story_id=STORY_ID,
            event_key=EVENT_KEY,
            chapter="CH00",
        )
    }

    app.state.story_event_conditions = {
        STORY_ID: StoryEventConditions(
            story_id=STORY_ID,
            chapter="CH00",
            all_evidence=frozenset({"E01"}),
            required_flags=frozenset({TRIGGER_FLAG}),
        )
    }

    django_client = Mock(spec=DjangoContentClient)

    django_client.get_approved_story_event.return_value = (
        ApprovedStoryEvent(
            event_key=EVENT_KEY,
            chapter="CH00",
            trigger_type="EVIDENCE_COLLECTED",
            required_evidence_ids=["E01"],
            title="Test event",
            text="Approved test content",
        )
    )

    app.state.django_content_client = django_client

    evaluator = PolicyEvaluator(
        {
            "POL-TEST-EVENT": AccessPolicy(
                required_evidence=["E01"],
                required_presentations=[],
                required_flags=[],
                required_ending=None,
                required_topics=[],
                required_disclosed_cards=[],
                required_character="C01",
            )
        }
    )

    trigger_rule = NPCTriggerRule(
        trigger_id="TRG-TEST-EVENT",
        character_id="C01",
        policy_id="POL-TEST-EVENT",
        topic="test-event",
        phrases=("verified action",),
        grant_flags=(TRIGGER_FLAG,),
    )

    def fake_dialogue(
        question,
        *,
        state,
        session_store,
        resources,
        policies,
        trigger_rules,
        presented_evidence_id,
    ):
        # 기존 서버 NPC Trigger 엔진을 실제 실행합니다.
        triggered = apply_npc_triggers(
            question,
            state=state,
            active_character_id="C01",
            rules=(trigger_rule,),
            evaluator=evaluator,
        )

        reply = NPCGroundedReply(
            text=FALLBACK_REPLY,
            source_ids=(),
            grounded=False,
        )

        exchange = session_store.append_verified_exchange(
            state,
            "C01",
            user_message=question,
            reply=reply,
        )

        return Case001DialogueResult(
            turn=NPCChatTurn(
                character_id="C01",
                reply=reply,
                exchange=exchange,
                display_text=FALLBACK_REPLY,
            ),
            state=triggered.state,
            presentation_created=False,
            trigger_ids=triggered.trigger_ids,
            disclosed_card_ids=(),
        )

    monkeypatch.setattr(
        atomic_module,
        "run_case001_npc_dialogue",
        fake_dialogue,
    )

    with TestClient(
        app,
        raise_server_exceptions=False,
    ) as client:
        session_id = start_game(client)

        before = repository.load_state(session_id)

        ready = GameState.model_validate(
            {
                **before.model_dump(mode="python"),
                "evidence": {
                    "E01": {"stage": "found"},
                },
                "outcome": None,
                "revision": before.revision + 1,
            }
        )

        repository.commit_state(
            expected_state=before,
            updated_state=ready,
        )

        yield (
            client,
            repository,
            session_id,
            django_client,
        )


def test_npc_trigger_and_event_commit_atomically(
    story_event_runtime,
):
    client, repository, session_id, django_client = (
        story_event_runtime
    )

    before = repository.load_state(session_id)

    response = client.post(
        f"/api/games/{session_id}/chat",
        json={"question": "verified action"},
    )

    assert response.status_code == 200, response.text

    saved = repository.load_state(session_id)

    assert TRIGGER_FLAG in saved.flags
    assert saved.queued_story_events == [STORY_ID]
    assert saved.revision == before.revision + 1

    assert len(
        repository.load_history(session_id, "C01")
    ) == 1

    assert repository.load_selection(session_id) == (
        "C01",
        saved.revision,
    )

    # 동일 조건으로 다시 대화해도 이벤트는 중복되지 않습니다.
    repeated = client.post(
        f"/api/games/{session_id}/chat",
        json={"question": "verified action"},
    )

    assert repeated.status_code == 200, repeated.text

    latest = repository.load_state(session_id)

    assert latest.queued_story_events == [STORY_ID]

    assert len(
        repository.load_history(session_id, "C01")
    ) == 2

    django_client.get_approved_story_event.assert_called_once_with(
        "CASE-001",
        EVENT_KEY,
    )


def test_npc_without_trigger_does_not_queue(
    story_event_runtime,
):
    client, repository, session_id, django_client = (
        story_event_runtime
    )

    response = client.post(
        f"/api/games/{session_id}/chat",
        json={"question": "hello"},
    )

    assert response.status_code == 200, response.text

    saved = repository.load_state(session_id)

    assert TRIGGER_FLAG not in saved.flags
    assert saved.queued_story_events == []

    django_client.get_approved_story_event.assert_not_called()


def test_npc_event_django_failure_does_not_commit(
    story_event_runtime,
):
    client, repository, session_id, django_client = (
        story_event_runtime
    )

    before = repository.load_state(session_id)

    django_client.get_approved_story_event.side_effect = (
        ContentServiceError("Django unavailable")
    )

    response = client.post(
        f"/api/games/{session_id}/chat",
        json={"question": "verified action"},
    )

    assert response.status_code == 503, response.text

    assert repository.load_state(session_id) == before

    assert repository.load_history(
        session_id,
        "C01",
    ) == ()

    assert repository.load_selection(session_id) == (
        "C01",
        before.revision,
    )


def test_npc_event_sqlite_failure_rolls_back(
    story_event_runtime,
    tmp_path,
):
    client, repository, session_id, django_client = (
        story_event_runtime
    )

    before = repository.load_state(session_id)

    # 대화 INSERT 단계에서 실제 SQLite 오류를 발생시킵니다.
    with sqlite3.connect(
        tmp_path / "game.sqlite3"
    ) as db:
        db.execute(
            """
            CREATE TRIGGER fail_event_exchange
            BEFORE INSERT ON npc_exchanges
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'injected story event failure'
                );
            END
            """
        )

    response = client.post(
        f"/api/games/{session_id}/chat",
        json={"question": "verified action"},
    )

    assert response.status_code == 500

    # Django 승인 조회 이후에도 DB 오류가 발생하면
    # 게임 상태와 이벤트 큐를 모두 롤백합니다.
    django_client.get_approved_story_event.assert_called_once()

    assert repository.load_state(session_id) == before

    assert repository.load_history(
        session_id,
        "C01",
    ) == ()

    assert repository.load_selection(session_id) == (
        "C01",
        before.revision,
    )


def test_day5_npc_story_context_lifecycle(
    story_event_runtime,
):
    client, repository, session_id, django_client = (
        story_event_runtime
    )

    service = StoryContextService(repository)
    bindings = client.app.state.story_event_bindings
    base = f"/api/games/{session_id}"

    def fetch_approved(event_key):
        return django_client.get_approved_story_event(
            "CASE-001",
            event_key,
        )

    def load_pending(state):
        return service.load_pending_event_keys(
            session_id,
            expected_revision=state.revision,
            bindings=bindings,
            fetch_approved_event=fetch_approved,
        )

    # 1. NPC 조사 이전 상태
    before = repository.load_state(session_id)

    context_before = service.load(
        session_id,
        expected_revision=before.revision,
    )

    assert TRIGGER_FLAG not in context_before.flags
    assert context_before.collected_evidence_ids == ("E01",)
    assert load_pending(before) == ()

    # 2. 실제 NPC API를 통해 Trigger 실행
    response = client.post(
        f"{base}/chat",
        json={"question": "verified action"},
    )

    assert response.status_code == 200, response.text

    after_chat = repository.load_state(session_id)

    # 3. Story Context에 변경된 상태 반영
    context_after = service.load(
        session_id,
        expected_revision=after_chat.revision,
    )

    assert TRIGGER_FLAG in context_after.flags
    assert context_after.revision == before.revision + 1
    assert context_after.current_chapter == "CH00"

    # 이전 revision으로는 맥락을 조회할 수 없습니다.
    with pytest.raises(ValueError, match="revision"):
        service.load(
            session_id,
            expected_revision=before.revision,
        )

    # 4. Agent Context와 Story Context 정합성
    agent_context = AgentContext.from_game_state(
        after_chat,
        active_character_id="C01",
    )

    assert agent_context.revision == context_after.revision
    assert (
        agent_context.current_chapter
        == context_after.current_chapter
    )
    assert (
        agent_context.collected_evidence_ids
        == context_after.collected_evidence_ids
    )

    # 5. Story Context와 HTTP Pending API의 결과 일치
    keys = load_pending(after_chat)

    pending = client.get(
        f"{base}/story-events/pending"
    )

    assert pending.status_code == 200

    http_keys = tuple(
        item["eventKey"]
        for item in pending.json()["items"]
    )

    assert keys == http_keys == (EVENT_KEY,)

    # 조회만 수행했으므로 상태는 변경되지 않습니다.
    assert repository.load_state(session_id) == after_chat

    # 6. 이벤트 확인
    ack = client.post(
        f"{base}/story-events/{EVENT_KEY}/ack"
    )

    assert ack.status_code == 200
    assert ack.json()["created"] is True

    after_ack = repository.load_state(session_id)

    assert after_ack.revision == after_chat.revision + 1
    assert after_ack.acknowledged_story_events == [STORY_ID]
    assert load_pending(after_ack) == ()

    # 7. 후속 NPC 대화에서도 이벤트가 재등록되지 않습니다.
    followup = client.post(
        f"{base}/chat",
        json={"question": "verified action"},
    )

    assert followup.status_code == 200, followup.text

    final = repository.load_state(session_id)

    assert final.queued_story_events == [STORY_ID]
    assert final.acknowledged_story_events == [STORY_ID]
    assert load_pending(final) == ()

    assert len(
        repository.load_history(session_id, "C01")
    ) == 2

    assert repository.load_selection(session_id) == (
        "C01",
        final.revision,
    )


def test_day5_story_context_survives_reconnect(
    story_event_runtime,
    tmp_path,
):
    client, repository, session_id, _ = (
        story_event_runtime
    )

    base = f"/api/games/{session_id}"

    response = client.post(
        f"{base}/chat",
        json={"question": "verified action"},
    )

    assert response.status_code == 200

    ack = client.post(
        f"{base}/story-events/{EVENT_KEY}/ack"
    )

    assert ack.status_code == 200

    saved = repository.load_state(session_id)

    # 기존 SQLite 파일을 새로운 저장소 인스턴스로 엽니다.
    reopened = SQLiteCase001Repository(
        tmp_path / "game.sqlite3"
    )

    restored = reopened.load_state(session_id)

    assert restored == saved

    context = StoryContextService(reopened).load(
        session_id,
        expected_revision=restored.revision,
    )

    assert TRIGGER_FLAG in context.flags
    assert context.current_chapter == "CH00"
    assert context.collected_evidence_ids == ("E01",)

    assert restored.queued_story_events == [STORY_ID]
    assert restored.acknowledged_story_events == [STORY_ID]

    assert reopened.load_selection(session_id) == (
        "C01",
        restored.revision,
    )

    assert (
        reopened.load_history(session_id, "C01")
        == repository.load_history(session_id, "C01")
    )

    # 기존 세션 재조회 시 확인한 이벤트는 표시되지 않습니다.
    resumed = client.get(base)

    assert resumed.status_code == 200
    assert resumed.json()["revision"] == saved.revision

    pending = client.get(
        f"{base}/story-events/pending"
    )

    assert pending.status_code == 200
    assert pending.json() == {"items": []}


def test_day5_npc_failure_preserves_story_context(
    story_event_runtime,
):
    client, repository, session_id, django_client = (
        story_event_runtime
    )

    service = StoryContextService(repository)

    before = repository.load_state(session_id)

    context_before = service.load(
        session_id,
        expected_revision=before.revision,
    )

    django_client.get_approved_story_event.side_effect = (
        ContentServiceError("Injected content service failure")
    )

    response = client.post(
        f"/api/games/{session_id}/chat",
        json={"question": "verified action"},
    )

    assert response.status_code == 503

    after = repository.load_state(session_id)

    context_after = service.load(
        session_id,
        expected_revision=after.revision,
    )

    # 실패한 대화의 Trigger 및 이벤트는 반영되지 않습니다.
    assert after == before
    assert context_after == context_before
    assert TRIGGER_FLAG not in context_after.flags

    assert after.queued_story_events == []
    assert after.acknowledged_story_events == []

    assert repository.load_history(
        session_id,
        "C01",
    ) == ()