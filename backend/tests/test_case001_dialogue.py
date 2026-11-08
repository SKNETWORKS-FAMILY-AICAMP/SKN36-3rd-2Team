"""Issue #24 - CASE-001 접근 정책과 NPC 대화 연결 테스트."""

from crimescene.chat.npc_chat_runtime import NPCChatTurn
from crimescene.chat.npc_rag_service import NPCRAGResources
from crimescene.chat.npc_session import NPCExchange, NPCSessionStore
from crimescene.retriever.npc_output_guard import NPCGroundedReply
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import EvidenceState, GameState
from crimescene.trigger import case001_dialogue
from crimescene.trigger.npc_trigger import NPCTriggerRule


def make_case():
    policy = AccessPolicy(
        required_evidence=["E05"],
        required_presentations=["C01:E05"],
        required_flags=[],
        required_ending=None,
        required_topics=["audit"],
        required_disclosed_cards=[],
        required_character="C01",
    )

    policies = {"POL-AUDIT": policy}

    cards = [
        {
            "id": "K-C01-01",
            "case_id": "CASE-001",
            "character_id": "C01",
            "policy_id": "POL-AUDIT",
            "body": "승인된 감사 자료의 진술입니다.",
            "access_scope": "character_only",
            "truth_status": "character_claim",
            "required_evidence": ["E05"],
            "required_presentations": ["C01:E05"],
            "required_flags": [],
            "required_ending": None,
            "required_topics": ["audit"],
            "required_disclosed_cards": [],
            "required_character": "C01",
            "supersedes": [],
            "stage_priority": 1,
        }
    ]

    evidences = {
        "E05": EvidenceRule(
            name="감사 기록",
            score=1,
            holder="C01",
            prerequisites=[],
            presentation=[],
            q=[],
        )
    }

    state = GameState(
        case_id="CASE-001",
        session_id="CASE001-ISSUE24-TEST",
        unlocked_characters=["C01"],
        evidence={"E05": EvidenceState(stage="found")},
        flags=[],
        presented={},
        attempts_left=3,
        score=0,
        outcome="ONGOING",
        deep_eligible=False,
        revision=0,
        disclosed_cards=[],
        document_grants=[],
    )

    # 실제 외부 DB 호출은 모킹하므로 클라이언트는 사용하지 않는다.
    resources = NPCRAGResources(
        personas={},
        qdrant_client=None,
        neo4j_driver=None,
        embedder=None,
        encoder=None,
        trusted_records=(),
        documents=(),
        npc_cards=tuple(cards),
        registry=(),
        trusted_edges=(),
        evidence_rules=evidences,
        evaluator=PolicyEvaluator(policies),
    )

    trigger = NPCTriggerRule(
        trigger_id="TRG-AUDIT",
        character_id="C01",
        policy_id="POL-AUDIT",
        topic="audit",
        phrases=("감사 자료",),
        grant_flags=("AUDIT_OPEN",),
    )

    store = NPCSessionStore()
    store.select_npc(state, "C01")

    return policies, cards, evidences, state, resources, trigger, store


def test_recipients_come_from_server_policies():
    policies, cards, evidences, *_ = make_case()

    allowed = case001_dialogue.build_case001_recipients(
        policies=policies,
        npc_cards=cards,
        evidence_rules=evidences,
    )

    assert allowed == {
        "E05": frozenset({"C01"}),
    }


def test_missing_policy_grants_nothing():
    _, cards, evidences, *_ = make_case()

    allowed = case001_dialogue.build_case001_recipients(
        policies={},
        npc_cards=cards,
        evidence_rules=evidences,
    )

    assert allowed == {}


def test_verified_reply_unlocks_only_quoted_card(monkeypatch):
    policies, _, _, original, resources, trigger, store = make_case()

    def fake_chat(
        query,
        *,
        state,
        session_store,
        resources,
        matched_topics,
        evidence_just_presented,
    ):
        assert state.presented == {"C01": ["E05"]}
        assert state.flags == ["AUDIT_OPEN"]
        assert matched_topics == ("audit",)
        assert evidence_just_presented is True

        return NPCChatTurn(
            character_id="C01",
            reply=NPCGroundedReply(
                text="검증된 응답",
                source_ids=("K-C01-01",),
                grounded=True,
            ),
            exchange=NPCExchange(
                query,
                "검증된 응답",
                ("K-C01-01",),
                state.revision,
            ),
        )

    monkeypatch.setattr(
        case001_dialogue,
        "run_npc_chat",
        fake_chat,
    )

    result = case001_dialogue.run_case001_npc_dialogue(
        "감사 자료를 확인했나요?",
        state=original,
        session_store=store,
        resources=resources,
        policies=policies,
        trigger_rules=(trigger,),
        presented_evidence_id="E05",
    )

    assert result.presentation_created
    assert result.trigger_ids == ("TRG-AUDIT",)
    assert result.disclosed_card_ids == ("K-C01-01",)

    assert result.state.disclosed_cards == ["K-C01-01"]
    assert result.state.revision == 3

    # 원본 상태는 변경되지 않아야 한다.
    assert original.disclosed_cards == []
    assert original.presented == {}


def test_unverified_reply_cannot_unlock_card(monkeypatch):
    policies, _, _, original, resources, trigger, store = make_case()

    def fake_chat(
        query,
        *,
        state,
        session_store,
        resources,
        matched_topics,
        evidence_just_presented,
    ):
        assert evidence_just_presented is True

        # 아래 기존 return NPCChatTurn(...) 코드는 그대로 유지
        return NPCChatTurn(
            character_id="C01",
            reply=NPCGroundedReply(
                text="근거 없음",
                source_ids=(),
                grounded=False,
            ),
            exchange=NPCExchange(
                query,
                "근거 없음",
                (),
                state.revision,
            ),
        )

    monkeypatch.setattr(
        case001_dialogue,
        "run_npc_chat",
        fake_chat,
    )

    result = case001_dialogue.run_case001_npc_dialogue(
        "감사 자료를 확인했나요?",
        state=original,
        session_store=store,
        resources=resources,
        policies=policies,
        trigger_rules=(trigger,),
        presented_evidence_id="E05",
    )

    assert result.disclosed_card_ids == ()
    assert result.state.disclosed_cards == []
    assert result.state.revision == 2


def test_unapproved_reply_source_cannot_unlock_card(monkeypatch):
    policies, _, _, original, resources, trigger, store = make_case()

    def fake_chat(
        query,
        *,
        state,
        session_store,
        resources,
        matched_topics,
        evidence_just_presented,
    ):
        assert evidence_just_presented is True

        # 아래 기존 return NPCChatTurn(...) 코드는 그대로 유지
        return NPCChatTurn(
            character_id="C01",
            reply=NPCGroundedReply(
                text="승인되지 않은 출처",
                source_ids=("K-C02-01",),
                grounded=True,
            ),
            exchange=NPCExchange(
                query,
                "승인되지 않은 출처",
                (),
                state.revision,
            ),
        )

    monkeypatch.setattr(
        case001_dialogue,
        "run_npc_chat",
        fake_chat,
    )

    result = case001_dialogue.run_case001_npc_dialogue(
        "감사 자료를 확인했나요?",
        state=original,
        session_store=store,
        resources=resources,
        policies=policies,
        trigger_rules=(trigger,),
        presented_evidence_id="E05",
    )

    assert result.disclosed_card_ids == ()
    assert result.state.disclosed_cards == []
