import pytest

from crimescene.scenario.npc_access import select_authorized_npc_cards
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.scenario.schemas.game_state import EvidenceState, GameState


def make_policy(*, evidence=(), character="C03"):
    return AccessPolicy(
        required_evidence=list(evidence),
        required_presentations=[],
        required_flags=[],
        required_ending=None,
        required_topics=[],
        required_disclosed_cards=[],
        required_character=character,
    )


def make_card(
    card_id,
    policy_id,
    *,
    character="C03",
    evidence=(),
    supersedes=(),
    priority=0,
    truth_status="character_claim",
):
    return {
        "id": card_id,
        "case_id": "CASE-001",
        "character_id": character,
        "policy_id": policy_id,
        "body": f"{card_id} 테스트 진술",
        "access_scope": "character_only",
        "truth_status": truth_status,
        "required_evidence": list(evidence),
        "required_presentations": [],
        "required_flags": [],
        "required_ending": None,
        "required_topics": [],
        "required_disclosed_cards": [],
        "required_character": character,
        "supersedes": list(supersedes),
        "stage_priority": priority,
    }


@pytest.fixture
def scenario():
    policies = {
        "POL-OLD": make_policy(),
        "POL-NEW": make_policy(evidence=["E05"]),
        "POL-SIDE": make_policy(),
        "POL-OTHER": make_policy(character="C04"),
    }

    cards = [
        make_card(
            "K-OLD",
            "POL-OLD",
            priority=0,
        ),
        make_card(
            "K-NEW",
            "POL-NEW",
            evidence=["E05"],
            supersedes=["K-OLD"],
            priority=2,
        ),
        make_card(
            "K-SIDE",
            "POL-SIDE",
            priority=1,
            truth_status="known_to_character",
        ),
        make_card(
            "K-OTHER",
            "POL-OTHER",
            character="C04",
            priority=3,
        ),
    ]

    state = GameState(
        case_id="CASE-001",
        session_id="TEST-SESSION",
        unlocked_characters=["C03"],
        evidence={},
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

    return cards, PolicyEvaluator(policies), state


def select(scenario, *, state=None, cards=None):
    original_cards, evaluator, original_state = scenario

    return select_authorized_npc_cards(
        original_cards if cards is None else cards,
        original_state if state is None else state,
        evaluator,
        active_character_id="C03",
    )


def card_ids(results):
    return [card.card_id for card in results]


def test_initial_statement_is_visible(scenario):
    """증거를 획득하기 전에는 초기 진술이 유지된다."""

    results = select(scenario)

    assert "K-OLD" in card_ids(results)
    assert "K-NEW" not in card_ids(results)


def test_unlocked_statement_replaces_old(scenario):
    """E05 획득 후 새로운 진술이 기존 진술을 대체한다."""

    _, _, state = scenario

    unlocked = state.model_copy(
        update={"evidence": {"E05": EvidenceState(stage="found")}}
    )

    results = select(scenario, state=unlocked)

    assert "K-NEW" in card_ids(results)
    assert "K-OLD" not in card_ids(results)


def test_locked_replacement_keeps_old(scenario):
    """새로운 진술이 잠겨 있으면 기존 진술을 유지한다."""

    results = select(scenario)

    assert "K-OLD" in card_ids(results)
    assert "K-NEW" not in card_ids(results)


def test_unrelated_statement_is_preserved(scenario):
    """대체 관계가 없는 다른 진술은 삭제하지 않는다."""

    _, _, state = scenario

    unlocked = state.model_copy(
        update={"evidence": {"E05": EvidenceState(stage="resolved")}}
    )

    results = select(scenario, state=unlocked)

    assert "K-SIDE" in card_ids(results)


def test_statement_priority_order(scenario):
    """공개된 진술은 stage_priority 내림차순으로 정렬한다."""

    _, _, state = scenario

    unlocked = state.model_copy(
        update={"evidence": {"E05": EvidenceState(stage="found")}}
    )

    results = select(scenario, state=unlocked)

    assert card_ids(results) == [
        "K-NEW",
        "K-SIDE",
    ]


def test_other_npc_knowledge_is_blocked(scenario):
    """C03 대화 중 C04의 지식을 노출하지 않는다."""

    results = select(scenario)

    assert "K-OTHER" not in card_ids(results)


def test_locked_npc_returns_nothing(scenario):
    """NPC 자체가 잠겨 있다면 모든 진술을 차단한다."""

    _, _, state = scenario

    locked = state.model_copy(update={"unlocked_characters": []})

    assert select(scenario, state=locked) == []


def test_unknown_policy_is_denied(scenario):
    """등록되지 않은 정책의 지식은 반환하지 않는다."""

    unknown_card = make_card(
        "K-UNKNOWN",
        "POL-UNKNOWN",
    )

    results = select(
        scenario,
        cards=[unknown_card],
    )

    assert results == []


def test_internal_metadata_is_excluded(scenario):
    """LLM에 전달할 결과에는 내부 접근 메타데이터가 없다."""

    results = select(scenario)

    assert results

    fields = set(results[0].model_dump())

    assert fields == {
        "card_id",
        "character_id",
        "content",
        "truth_status",
    }

    assert "protected_fact_ids" not in fields
    assert "source_refs" not in fields
    assert "supersedes" not in fields
