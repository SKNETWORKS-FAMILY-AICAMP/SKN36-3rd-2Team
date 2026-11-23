
"""Issue #131 - NPC Agent와 SQLite 원자적 저장 통합 테스트."""

from unittest.mock import Mock

from fastapi.testclient import TestClient

import crimescene.trigger.atomic_dialogue as atomic_module
from crimescene.api.app import create_app
from crimescene.chat.npc_chat_runtime import NPCChatTurn
from crimescene.chat.npc_rag_service import NPCRAGResources
from crimescene.retriever.npc_output_guard import NPCGroundedReply
from crimescene.retriever.npc_response_gate import FALLBACK_REPLY
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository
from crimescene.trigger.case001_dialogue import Case001DialogueResult


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
