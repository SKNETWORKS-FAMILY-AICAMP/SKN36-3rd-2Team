"""Issue #63 - API 런타임 DI와 실제 SQLite 커밋 경로 검증."""

from fastapi.testclient import TestClient

import crimescene.api.app as api_module
from crimescene.api.app import create_app
from crimescene.chat.npc_chat_runtime import NPCChatTurn
from crimescene.chat.npc_session import NPCExchange
from crimescene.retriever.npc_output_guard import NPCGroundedReply
from crimescene.retriever.npc_response_gate import FALLBACK_REPLY
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository
from crimescene.trigger.case001_dialogue import Case001DialogueResult


def test_app_state_resources_are_used_for_chat(tmp_path, monkeypatch):
    repository = SQLiteCase001Repository(tmp_path / "game.sqlite3")
    app = create_app(repository, session_secret="test-secret-" + "a" * 32)

    dummy_resources = object()
    app.state.dialogue_resources = dummy_resources
    app.state.dialogue_policies = {}
    app.state.dialogue_triggers = ()
    app.state.dialogue_flag_config = None

    def fake_atomic(
        question,
        *,
        session_id,
        repository,
        resources,
        policies,
        trigger_rules,
        presented_evidence_id=None,
        flag_config=None,
    ):
        assert resources is dummy_resources
        assert policies == {}
        assert trigger_rules == ()
        assert question == "안녕하세요."
        assert presented_evidence_id is None
        state = repository.load_state(session_id)
        reply = NPCGroundedReply(text=FALLBACK_REPLY, source_ids=(), grounded=False)
        turn = NPCChatTurn(
            character_id="C01",
            reply=reply,
            exchange=NPCExchange(
                user_message=question,
                npc_message=FALLBACK_REPLY,
                source_ids=(),
                state_revision=state.revision,
            ),
            display_text=FALLBACK_REPLY,
        )
        committed = repository.commit_turn(
            expected_state=state, updated_state=state, turn=turn
        )
        return Case001DialogueResult(
            turn=turn,
            state=committed,
            presentation_created=False,
            trigger_ids=(),
            disclosed_card_ids=(),
        )

    monkeypatch.setattr(api_module, "run_case001_npc_dialogue_atomic", fake_atomic)

    with TestClient(app) as client:
        created = client.post("/api/games")
        assert created.status_code == 201
        session_id = created.json()["sessionId"]
        assert (
            client.post(f"/api/games/{session_id}/prologue/complete").status_code == 200
        )
        result = client.post(
            f"/api/games/{session_id}/chat", json={"question": "안녕하세요."}
        )
        assert result.status_code == 200, result.text
        assert result.json()["characterId"] == "C01"
        assert result.json()["display_text"] == FALLBACK_REPLY
        assert result.json()["game"]["revision"] == 2

    assert len(repository.load_history(session_id, "C01")) == 1


def test_missing_private_data_fails_closed(tmp_path, monkeypatch):
    import pytest

    from crimescene.api.chat_bootstrap import load_chat_runtime
    from crimescene.settings import settings

    monkeypatch.setattr(settings, "ollama_model", "dummy-for-test")
    monkeypatch.setenv("CRIMESCENE_CASE001_ROOT", str(tmp_path / "missing"))
    # 데이터가 없는 환경에서는 실제 검색 서비스를 실행하지 않습니다.
    with pytest.raises(FileNotFoundError), load_chat_runtime():
        pass
