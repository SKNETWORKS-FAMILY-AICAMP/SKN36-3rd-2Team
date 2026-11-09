import pytest

import crimescene.trigger.case001_dialogue as dialogue_module
from crimescene.chat.npc_chat_runtime import NPCChatTurn
from crimescene.chat.npc_rag_service import NPCRAGResources
from crimescene.retriever.npc_output_guard import NPCGroundedReply
from crimescene.retriever.npc_response_gate import FALLBACK_REPLY
from crimescene.scenario.game_progress import create_initial_state
from crimescene.scenario.loaders.unlock_graph_loader import (
    Case001UnlockRules,
)
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import (
    EvidenceState,
    GamePhase,
)
from crimescene.trigger.atomic_dialogue import (
    SQLiteCase001Repository,
    run_case001_npc_dialogue_atomic,
)
from crimescene.trigger.npc_trigger import NPCTriggerRule


@pytest.mark.parametrize(
    ("collected", "expected_flags"),
    [
        (True, ["L04"]),
        (False, []),
    ],
)
def test_atomic_flag_persistence(
    tmp_path,
    monkeypatch,
    collected,
    expected_flags,
):
    session_id = f"issue28-atomic-{collected}"

    repository = SQLiteCase001Repository(tmp_path / "case001.sqlite3")

    state = create_initial_state(session_id).model_copy(
        update={
            "phase": GamePhase.INVESTIGATION,
            "evidence": ({"E01": EvidenceState(stage="found")} if collected else {}),
            "score": 1 if collected else 0,
        }
    )

    repository.save_selection(
        session_id,
        "C01",
        state.revision,
    )
    repository.register_state(state)

    policy = AccessPolicy(
        required_evidence=["E01"],
        required_presentations=[],
        required_flags=[],
        required_ending=None,
        required_topics=["meeting"],
        required_disclosed_cards=[],
        required_character="C01",
    )

    policies = {"POL-MEETING": policy}

    evaluator = PolicyEvaluator(policies)

    resources = NPCRAGResources(
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
        evidence_rules={
            "E01": EvidenceRule(
                name="첫 번째 증거",
                score=1,
                holder="C01",
                prerequisites=[],
                presentation=[],
                q=[],
            )
        },
        evaluator=evaluator,
    )

    trigger = NPCTriggerRule(
        trigger_id="TRG-MEETING",
        character_id="C01",
        policy_id="POL-MEETING",
        topic="meeting",
        phrases=("회의",),
        grant_flags=(),
    )

    config = Case001UnlockRules(
        npc_rules={},
        flag_requirements={
            "L04": frozenset({"E01"}),
        },
        flag_sources={
            "L04": "C01 E01 Q:meeting or C10 Q:1405",
        },
    )

    # 외부 LLM/RAG만 대체하고 실제 세션 저장 로직은 사용합니다.
    def fake_chat(
        query,
        *,
        state,
        session_store,
        resources,
        matched_topics,
        evidence_just_presented,
    ):
        reply = NPCGroundedReply(
            text=FALLBACK_REPLY,
            source_ids=(),
            grounded=False,
        )

        exchange = session_store.append_verified_exchange(
            state,
            "C01",
            user_message=query,
            reply=reply,
        )

        return NPCChatTurn(
            character_id="C01",
            reply=reply,
            exchange=exchange,
        )

    monkeypatch.setattr(
        dialogue_module,
        "run_npc_chat",
        fake_chat,
    )

    result = run_case001_npc_dialogue_atomic(
        "회의에 대해 알려주세요.",
        session_id=session_id,
        repository=repository,
        resources=resources,
        policies=policies,
        trigger_rules=(trigger,),
        flag_config=config,
    )

    saved = repository.load_state(session_id)

    # 검증된 정책과 선행 증거에 따라 플래그가 지급됩니다.
    assert result.state.flags == expected_flags
    assert saved.flags == expected_flags

    # 게임 상태와 대화 기록이 동일 트랜잭션으로 저장됩니다.
    assert saved == result.state
    assert repository.load_history(session_id, "C01") == (result.turn.exchange,)

    # NPC 세션 revision도 동일하게 갱신됩니다.
    assert repository.load_selection(session_id) == (
        "C01",
        result.state.revision,
    )
