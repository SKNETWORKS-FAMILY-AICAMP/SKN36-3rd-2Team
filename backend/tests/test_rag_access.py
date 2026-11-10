import json
from pathlib import Path

import pytest

from crimescene.scenario.loaders.access_policy_loader import (
    load_access_policies,
)
from crimescene.scenario.loaders.document_loader import (
    load_player_documents,
)
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.rag_access import (
    build_authorized_rag_context,
)
from crimescene.scenario.schemas.game_state import (
    EvidenceState,
    GamePhase,
    GameState,
)


@pytest.fixture(scope="module")
def case_data():
    """로컬 v7.1 원본 데이터를 읽는다."""

    root = Path(__file__).resolve().parents[2] / ".local" / "case001_v7_1"

    matches = list(root.glob("*/data/access_policies.json"))

    if not matches:
        pytest.skip("로컬 v7.1 데이터가 없어 통합 테스트 생략")

    assert len(matches) == 1
    data_dir = matches[0].parent

    policies = load_access_policies(data_dir / "access_policies.json")

    documents = load_player_documents(data_dir / "player_documents.jsonl")

    cards = [
        json.loads(line)
        for line in (data_dir / "npc_knowledge_cards.jsonl")
        .read_text(encoding="utf-8-sig")
        .splitlines()
        if line.strip()
    ]

    assert len(policies) == 153
    assert len(documents) == 28
    assert len(cards) == 88

    return policies, documents, cards


def _value(item, field):
    if isinstance(item, dict):
        return item.get(field)
    return getattr(item, field)


def _make_satisfied_state(policy, item, *, npc_id=None):
    """정책과 데이터 자체의 요구 조건을 충족하는 테스트 상태."""

    def requirements(field):
        policy_values = set(getattr(policy, field))

        # NPC 카드 원본은 모든 접근 조건 필드를 포함
        if isinstance(item, dict):
            return policy_values | set(_value(item, field))

        # PlayerDocument에는 존재하지 않는 필드
        # 해당 조건은 AccessPolicy에서 확인
        if field in {
            "required_topics",
            "required_disclosed_cards",
        }:
            return policy_values

        # 문서 자체에 정의된 접근 조건도 함께 검사
        return policy_values | set(_value(item, field))

    presentations = requirements("required_presentations")
    evidence_ids = requirements("required_evidence")

    presented = {}

    for presentation in presentations:
        character_id, evidence_id = presentation.split(":")
        evidence_ids.add(evidence_id)
        presented.setdefault(character_id, []).append(evidence_id)

    endings = {
        value
        for value in (
            policy.required_ending,
            _value(item, "required_ending"),
        )
        if value is not None
    }

    assert len(endings) <= 1, "서로 충돌하는 엔딩 조건"

    character_id = npc_id or policy.required_character

    if (
        policy.required_character is not None
        and character_id != policy.required_character
    ):
        raise AssertionError("NPC 접근 정책 불일치")

    state = GameState(
        case_id=_value(item, "case_id"),
        session_id="RAG-INTEGRATION-TEST",
        phase=(
            GamePhase.FINISHED
            if endings
            else GamePhase.INVESTIGATION
        ),
        unlocked_characters=([character_id] if character_id else []),
        evidence={
            evidence_id: EvidenceState(stage="found")
            for evidence_id in evidence_ids
        },
        flags=sorted(requirements("required_flags")),
        presented=presented,
        attempts_left=3,
        score=0,
        outcome=(
            "SUCCESS"
            if "DEEP" in endings
            else next(iter(endings), "ONGOING")
        ),
        deep_eligible="DEEP" in endings,
        revision=0,
        disclosed_cards=sorted(requirements("required_disclosed_cards")),
        document_grants=[],
    )

    return state, requirements("required_topics")


@pytest.mark.parametrize("index", range(28))
def test_all_player_documents_are_policy_controlled(case_data, index):
    policies, documents, _ = case_data

    document = documents[index]
    policy = policies[document.policy_id]

    state, topics = _make_satisfied_state(policy, document)

    evaluator = PolicyEvaluator(policies)

    chunks = build_authorized_rag_context(
        documents=[document],
        npc_cards=[],
        state=state,
        evaluator=evaluator,
        matched_topics=topics,
    )

    assert len(chunks) == 1
    assert chunks[0].source_id == document.doc_id
    assert chunks[0].source_type == "player_document"

    # 내부 보호 정보가 반환되는 구조인지 확인
    assert set(chunks[0].model_dump()) == {
        "source_id",
        "source_type",
        "content",
        "truth_status",
        "character_id",
    }


@pytest.mark.parametrize("index", range(88))
def test_all_npc_cards_are_policy_controlled(case_data, index):
    policies, _, cards = case_data

    card = cards[index]
    policy = policies[card["policy_id"]]

    state, topics = _make_satisfied_state(
        policy,
        card,
        npc_id=card["character_id"],
    )

    evaluator = PolicyEvaluator(policies)

    chunks = build_authorized_rag_context(
        documents=[],
        npc_cards=[card],
        state=state,
        evaluator=evaluator,
        active_character_id=card["character_id"],
        matched_topics=topics,
    )

    assert len(chunks) == 1
    assert chunks[0].source_id == card["id"]
    assert chunks[0].source_type == "npc_knowledge"
    assert chunks[0].truth_status == card["truth_status"]


@pytest.mark.parametrize("kind", ["document", "npc"])
def test_missing_evidence_blocks_rag_context(case_data, kind):
    policies, documents, cards = case_data

    items = documents if kind == "document" else cards

    item = next(
        item
        for item in items
        if (
            _value(item, "required_evidence")
            or policies[_value(item, "policy_id")].required_evidence
        )
    )

    policy = policies[_value(item, "policy_id")]

    npc_id = item["character_id"] if kind == "npc" else None

    state, topics = _make_satisfied_state(policy, item, npc_id=npc_id)

    # 반드시 필요한 증거를 제거
    state = state.model_copy(update={"evidence": {}})

    chunks = build_authorized_rag_context(
        documents=[item] if kind == "document" else [],
        npc_cards=[item] if kind == "npc" else [],
        state=state,
        evaluator=PolicyEvaluator(policies),
        active_character_id=npc_id,
        matched_topics=topics,
    )

    assert chunks == []


def test_locked_npc_cannot_leak_information(case_data):
    policies, _, cards = case_data

    card = cards[0]
    policy = policies[card["policy_id"]]

    state, topics = _make_satisfied_state(
        policy,
        card,
        npc_id=card["character_id"],
    )

    state = state.model_copy(update={"unlocked_characters": []})

    chunks = build_authorized_rag_context(
        documents=[],
        npc_cards=[card],
        state=state,
        evaluator=PolicyEvaluator(policies),
        active_character_id=card["character_id"],
        matched_topics=topics,
    )

    assert chunks == []


def test_admin_scope_cannot_enter_player_context(case_data):
    policies, documents, _ = case_data

    document = documents[0]
    policy = policies[document.policy_id]

    state, topics = _make_satisfied_state(policy, document)

    # 모델 내부에서 비허용 등급이 들어오는 상황을 모의
    admin_document = document.model_copy(update={"access_scope": "admin_only"})

    chunks = build_authorized_rag_context(
        documents=[admin_document],
        npc_cards=[],
        state=state,
        evaluator=PolicyEvaluator(policies),
        matched_topics=topics,
    )

    assert chunks == []


def test_unknown_policy_cannot_enter_rag_context(case_data):
    policies, documents, _ = case_data

    document = documents[0]
    policy = policies[document.policy_id]

    state, topics = _make_satisfied_state(policy, document)

    invalid_document = document.model_copy(update={"policy_id": "POL-UNKNOWN"})

    chunks = build_authorized_rag_context(
        documents=[invalid_document],
        npc_cards=[],
        state=state,
        evaluator=PolicyEvaluator(policies),
        matched_topics=topics,
    )

    assert chunks == []


def test_player_documents_are_not_exposed_to_npc_context(case_data):
    """플레이어가 볼 수 있는 문서라도 NPC에게 자동 공개하지 않는다."""

    policies, documents, _ = case_data

    document = documents[0]
    policy = policies[document.policy_id]

    state, topics = _make_satisfied_state(
        policy,
        document,
    )

    state = state.model_copy(update={"unlocked_characters": ["C03"]})

    evaluator = PolicyEvaluator(policies)

    # 플레이어 조사 모드에서는 정상 접근 가능
    player_chunks = build_authorized_rag_context(
        documents=[document],
        npc_cards=[],
        state=state,
        evaluator=evaluator,
        matched_topics=topics,
    )

    assert len(player_chunks) == 1

    # NPC 대화 모드에서는 플레이어 문서를 자동 전달하지 않음
    npc_chunks = build_authorized_rag_context(
        documents=[document],
        npc_cards=[],
        state=state,
        evaluator=evaluator,
        active_character_id="C03",
        matched_topics=topics,
    )

    assert npc_chunks == []
