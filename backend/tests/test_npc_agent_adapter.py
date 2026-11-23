"""Issue #131 - NPC Agent Adapter 단위 테스트."""

from unittest.mock import Mock

import pytest

from crimescene.agents.contracts import (
    AgentContext,
    AgentRequest,
    AgentType,
)
from crimescene.agents.npc_agent import NPCAgent, NPCAgentResult
from crimescene.chat.npc_chat_runtime import NPCChatTurn
from crimescene.chat.npc_rag_service import NPCRAGResources
from crimescene.chat.npc_session import NPCExchange
from crimescene.retriever.npc_output_guard import NPCGroundedReply
from crimescene.scenario.game_progress import create_initial_state
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository
from crimescene.trigger.case001_dialogue import Case001DialogueResult


def make_agent():
    repository = Mock(spec=SQLiteCase001Repository)
    resources = Mock(spec=NPCRAGResources)
    resources.npc_cards = []
    resources.evidence_rules = {}

    return NPCAgent(
        repository=repository,
        resources=resources,
        policies={},
    )


def make_context():
    state = create_initial_state("session-131")
    return AgentContext.from_game_state(
        state,
        active_character_id="C01",
    )


def test_npc_agent_type():
    agent = make_agent()
    assert agent.agent_type == AgentType.NPC


def test_npc_agent_rejects_other_agent_type():
    agent = make_agent()

    with pytest.raises(ValueError, match="NPC Agent"):
        agent.execute(
            AgentRequest(
                agent_type=AgentType.HINT,
                message="힌트",
            ),
            context=make_context(),
        )


def test_npc_agent_rejects_uncollected_evidence():
    agent = make_agent()

    with pytest.raises(PermissionError, match="수집하지 않은"):
        agent.execute(
            AgentRequest(
                agent_type=AgentType.NPC,
                message="이 증거를 보세요",
                presented_evidence_id="E01",
            ),
            context=make_context(),
        )


def test_npc_agent_reuses_atomic_dialogue(monkeypatch):
    calls = []
    context = make_context()

    def fake_atomic(question, **kwargs):
        calls.append((question, kwargs))

        state = create_initial_state(context.session_id)

        reply = NPCGroundedReply(
            text="안녕하세요.",
            source_ids=(),
            grounded=False,
        )

        return Case001DialogueResult(
            turn=NPCChatTurn(
                character_id="C01",
                reply=reply,
                exchange=NPCExchange(
                    user_message=question,
                    npc_message="안녕하세요.",
                    source_ids=(),
                    state_revision=state.revision,
                ),
                display_text="안녕하세요.",
            ),
            state=state,
            presentation_created=False,
            trigger_ids=(),
            disclosed_card_ids=(),
        )

    monkeypatch.setattr(
        "crimescene.agents.npc_agent.run_case001_npc_dialogue_atomic",
        fake_atomic,
    )

    result = make_agent().execute(
        AgentRequest(
            agent_type=AgentType.NPC,
            message="안녕하세요",
        ),
        context=context,
    )

    assert isinstance(result, NPCAgentResult)
    assert result.text == "안녕하세요."
    assert result.dialogue.turn.character_id == "C01"
    assert len(calls) == 1
    assert calls[0][0] == "안녕하세요"
    assert calls[0][1]["session_id"] == "session-131"

    # 내부 GameState와 대화 원본은 공개 직렬화에서 제외
    assert "dialogue" not in result.model_dump()