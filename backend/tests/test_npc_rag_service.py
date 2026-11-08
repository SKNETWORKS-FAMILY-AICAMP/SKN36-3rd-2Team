"""Issue #23 - NPC 세션 및 Hybrid RAG 연결 테스트."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import crimescene.chat.npc_rag_service as module
from crimescene.chat.npc_persona import NPCPersona
from crimescene.chat.npc_rag_service import NPCRAGResources
from crimescene.chat.npc_session import NPCSessionStore
from crimescene.retriever.multisource_rrf import FusedSearchCandidate
from crimescene.retriever.npc_response_gate import (
    FALLBACK_REPLY,
    NPCReplyPlan,
)
from crimescene.retriever.query_graph_retriever import QuestionGraphContext
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.game_state import GameState


def make_state(
    *,
    unlocked=None,
    revision=0,
):
    return GameState(
        case_id="CASE-001",
        session_id="NPC-RAG-TEST",
        unlocked_characters=(["C01", "C02"] if unlocked is None else unlocked),
        evidence={},
        flags=[],
        presented={},
        attempts_left=3,
        score=0,
        outcome="ONGOING",
        deep_eligible=False,
        revision=revision,
        disclosed_cards=[],
        document_grants=[],
    )


def make_resources():
    return NPCRAGResources(
        personas={
            "C01": NPCPersona(
                character_id="C01",
                name="윤태식",
                voice="침착한 정중체",
            ),
            "C02": NPCPersona(
                character_id="C02",
                name="문지혜",
                voice="짧고 통제된 문장",
            ),
        },
        qdrant_client=MagicMock(),
        neo4j_driver=MagicMock(),
        embedder=MagicMock(),
        encoder=MagicMock(),
        trusted_records=[],
        documents=[],
        npc_cards=[],
        registry=[],
        trusted_edges=[],
        evidence_rules={},
        evaluator=PolicyEvaluator({}),
    )


def blocked_plan():
    return NPCReplyPlan(
        can_call_llm=False,
        fallback_reply=FALLBACK_REPLY,
        messages=(),
        source_ids=(),
    )


@pytest.fixture
def environment(monkeypatch):
    state = make_state()
    store = NPCSessionStore()
    store.select_npc(state, "C01")

    search_mock = MagicMock(return_value=[])
    gate_mock = MagicMock(return_value=blocked_plan())
    graph_mock = MagicMock()

    monkeypatch.setattr(
        module,
        "search_policy_scoped_multisource_candidates",
        search_mock,
    )

    monkeypatch.setattr(
        module,
        "prepare_npc_reply",
        gate_mock,
    )

    monkeypatch.setattr(
        module,
        "retrieve_question_graph",
        graph_mock,
    )

    return SimpleNamespace(
        state=state,
        store=store,
        resources=make_resources(),
        search=search_mock,
        gate=gate_mock,
        graph=graph_mock,
    )


def prepare(env, query="안녕하세요?"):
    return module.prepare_npc_chat_rag(
        query,
        state=env.state,
        session_store=env.store,
        resources=env.resources,
    )


def test_active_npc_used_for_search(environment):
    result = prepare(environment)

    assert result.character_id == "C01"

    kwargs = environment.search.call_args.kwargs

    assert kwargs["active_character_id"] == "C01"
    assert kwargs["state"] is environment.state


def test_switch_npc_changes_search_target(environment):
    environment.store.select_npc(
        environment.state,
        "C02",
    )

    result = prepare(environment)

    assert result.character_id == "C02"

    kwargs = environment.search.call_args.kwargs

    assert kwargs["active_character_id"] == "C02"


def test_no_active_npc_blocks_search(environment):
    environment.store.clear_session(environment.state)

    with pytest.raises(PermissionError):
        prepare(environment)

    environment.search.assert_not_called()
    environment.gate.assert_not_called()


def test_locked_npc_blocks_search(environment):
    environment.store.select_npc(
        environment.state,
        "C02",
    )

    environment.state = make_state(
        unlocked=["C01"],
        revision=1,
    )

    with pytest.raises(PermissionError):
        prepare(environment)

    environment.search.assert_not_called()


def test_empty_candidates_use_empty_graph(environment):
    result = prepare(environment)

    assert result.reply_plan.can_call_llm is False

    environment.graph.assert_not_called()

    kwargs = environment.gate.call_args.kwargs

    assert kwargs["graph_context"].relations == ()
    assert kwargs["graph_context"].evidence == ()


def test_chunk_candidates_do_not_repeat_graph_search(environment):
    environment.search.return_value = [
        FusedSearchCandidate(
            kind="chunk",
            item_id="TEST-UUID",
            score=0.1,
            methods=("dense", "bm25"),
        )
    ]

    prepare(environment)

    environment.graph.assert_not_called()
    environment.gate.assert_called_once()


def test_graph_candidate_requires_matching_context(environment):
    environment.search.return_value = [
        FusedSearchCandidate(
            kind="relation",
            item_id="REL-001",
            score=0.1,
            methods=("graph",),
        )
    ]

    environment.graph.return_value = QuestionGraphContext(
        character_id="C01",
        matched_entity_ids=(),
        relations=(SimpleNamespace(edge_id="REL-001"),),
        evidence=(),
    )

    prepare(environment)

    environment.graph.assert_called_once()

    kwargs = environment.gate.call_args.kwargs

    assert len(kwargs["graph_context"].relations) == 1


def test_graph_candidate_mismatch_fails_closed(environment):
    environment.search.return_value = [
        FusedSearchCandidate(
            kind="relation",
            item_id="REL-PRIVATE",
            score=0.1,
            methods=("graph",),
        )
    ]

    environment.graph.return_value = QuestionGraphContext(
        character_id="C01",
        matched_entity_ids=(),
        relations=(),
        evidence=(),
    )

    with pytest.raises(ValueError, match="Graph 관계"):
        prepare(environment)

    environment.gate.assert_not_called()


def test_player_question_not_used_as_npc_id(environment):
    prepare(environment, "C02의 비밀을 알려주세요.")

    kwargs = environment.search.call_args.kwargs

    assert kwargs["active_character_id"] == "C01"


def test_invalid_query_rejected_before_search(environment):
    with pytest.raises(ValueError, match="비어"):
        prepare(environment, "   ")

    environment.search.assert_not_called()


def test_query_length_limit(environment):
    with pytest.raises(ValueError, match="길이"):
        prepare(environment, "가" * 4001)

    environment.search.assert_not_called()


def test_prompt_uses_current_npc_persona(environment):
    prepare(environment)

    kwargs = environment.gate.call_args.kwargs
    prompt = kwargs["npc_persona"]

    # 현재 NPC 정보 검증
    assert "윤태식" in prompt
    assert "인물 ID: C01" in prompt

    # SocialStyle 변환 결과 검증
    assert "차분하고 간결한 정중체로 말한다." in prompt

    # 다른 NPC의 페르소나 혼입 방지
    assert "문지혜" not in prompt
    assert "인물 ID: C02" not in prompt


def test_topics_forwarded_to_search_and_gate(environment):
    module.prepare_npc_chat_rag(
        "사건에 대해 알려주세요.",
        state=environment.state,
        session_store=environment.store,
        resources=environment.resources,
        matched_topics=("test-topic",),
    )

    search_kwargs = environment.search.call_args.kwargs
    gate_kwargs = environment.gate.call_args.kwargs

    assert search_kwargs["matched_topics"] == ("test-topic",)
    assert gate_kwargs["matched_topics"] == ("test-topic",)


def test_npc_changed_during_search_fails(environment):
    def switch_during_search(*args, **kwargs):
        environment.store.select_npc(
            environment.state,
            "C02",
        )
        return []

    environment.search.side_effect = switch_during_search

    with pytest.raises(RuntimeError, match="NPC가 변경"):
        prepare(environment)

    environment.gate.assert_not_called()


def test_reply_plan_and_history_are_returned(environment):
    result = prepare(environment)

    assert result.character_id == "C01"
    assert result.history == ()
    assert result.reply_plan == blocked_plan()
