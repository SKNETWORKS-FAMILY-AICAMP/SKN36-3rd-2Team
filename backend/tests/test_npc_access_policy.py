import pytest
from pydantic import ValidationError

from crimescene.scenario.access_policy import (
    NPCDisclosureContext,
    can_disclose_knowledge,
    select_disclosable_knowledge,
)
from crimescene.scenario.npc_knowledge import (
    DisclosureCondition,
    DisclosureRule,
    KnowledgeType,
    NPCKnowledgeCard,
)


def make_card(
    npc_id="NPC-001",
    condition=DisclosureCondition.OPEN,
    reference_id=None,
    knowledge_id="K-001",
):
    """테스트용 NPC 지식 카드 생성."""

    return NPCKnowledgeCard(
        knowledge_id=knowledge_id,
        npc_id=npc_id,
        knowledge_type=KnowledgeType.OBSERVATION,
        content="테스트용 NPC 지식입니다.",
        disclosure_rule=DisclosureRule(
            condition=condition,
            reference_id=reference_id,
        ),
    )


def test_open_knowledge_allowed():
    """자신의 공개 지식은 조회할 수 있다."""

    card = make_card()
    context = NPCDisclosureContext(npc_id="NPC-001")

    assert can_disclose_knowledge(card, context) is True


def test_other_npc_knowledge_blocked():
    """다른 NPC의 지식은 접근할 수 없다."""

    card = make_card(npc_id="NPC-002")
    context = NPCDisclosureContext(npc_id="NPC-001")

    assert can_disclose_knowledge(card, context) is False


@pytest.mark.parametrize(
    ("matched_ids", "expected"),
    [
        (frozenset(), False),
        (frozenset({"Q-001"}), True),
    ],
)
def test_question_condition(matched_ids, expected):
    """관련 질문 조건을 확인한다."""

    card = make_card(
        condition=DisclosureCondition.QUESTION,
        reference_id="Q-001",
    )

    context = NPCDisclosureContext(
        npc_id="NPC-001",
        matched_question_ids=matched_ids,
    )

    assert can_disclose_knowledge(card, context) is expected


@pytest.mark.parametrize(
    ("collected_ids", "expected"),
    [
        (frozenset(), False),
        (frozenset({"EVD-001"}), True),
    ],
)
def test_evidence_collected_condition(collected_ids, expected):
    """증거 획득 여부에 따라 정보를 공개한다."""

    card = make_card(
        condition=DisclosureCondition.EVIDENCE_COLLECTED,
        reference_id="EVD-001",
    )

    context = NPCDisclosureContext(
        npc_id="NPC-001",
        collected_evidence_ids=collected_ids,
    )

    assert can_disclose_knowledge(card, context) is expected


@pytest.mark.parametrize(
    ("collected", "presented", "expected"),
    [
        (False, False, False),
        (False, True, False),
        (True, False, False),
        (True, True, True),
    ],
)
def test_evidence_presented_condition(
    collected,
    presented,
    expected,
):
    """증거를 획득하고 제시해야 정보를 공개한다."""

    card = make_card(
        condition=DisclosureCondition.EVIDENCE_PRESENTED,
        reference_id="EVD-001",
    )

    context = NPCDisclosureContext(
        npc_id="NPC-001",
        collected_evidence_ids=(frozenset({"EVD-001"}) if collected else frozenset()),
        presented_evidence_ids=(frozenset({"EVD-001"}) if presented else frozenset()),
    )

    assert can_disclose_knowledge(card, context) is expected


@pytest.mark.parametrize(
    ("unlocked_ids", "expected"),
    [
        (frozenset(), False),
        (frozenset({"FLAG-001"}), True),
    ],
)
def test_flag_unlock_condition(unlocked_ids, expected):
    """게임 이벤트 해금 여부를 확인한다."""

    card = make_card(
        condition=DisclosureCondition.FLAG_UNLOCKED,
        reference_id="FLAG-001",
    )

    context = NPCDisclosureContext(
        npc_id="NPC-001",
        unlocked_flag_ids=unlocked_ids,
    )

    assert can_disclose_knowledge(card, context) is expected


def test_select_only_allowed_knowledge():
    """여러 지식 중 허용된 정보만 반환한다."""

    cards = [
        make_card(
            npc_id="NPC-001",
            knowledge_id="K-001",
        ),
        make_card(
            npc_id="NPC-002",
            knowledge_id="K-002",
        ),
        make_card(
            npc_id="NPC-001",
            knowledge_id="K-003",
            condition=DisclosureCondition.EVIDENCE_COLLECTED,
            reference_id="EVD-001",
        ),
    ]

    context = NPCDisclosureContext(npc_id="NPC-001")

    result = select_disclosable_knowledge(cards, context)

    assert len(result) == 1
    assert result[0].knowledge_id == "K-001"

    # 내부 메타데이터는 반환하지 않는다.
    output = result[0].model_dump()

    assert "npc_id" not in output
    assert "disclosure_rule" not in output
    assert "source_refs" not in output


@pytest.mark.parametrize(
    "condition",
    [
        DisclosureCondition.QUESTION,
        DisclosureCondition.EVIDENCE_COLLECTED,
        DisclosureCondition.EVIDENCE_PRESENTED,
        DisclosureCondition.FLAG_UNLOCKED,
    ],
)
def test_missing_reference_id_rejected(condition):
    """조건부 공개에는 참조 ID가 필요하다."""

    with pytest.raises(ValidationError):
        DisclosureRule(
            condition=condition,
            reference_id=None,
        )


def test_open_condition_rejects_reference_id():
    """OPEN 조건에는 참조 ID를 지정할 수 없다."""

    with pytest.raises(ValidationError):
        DisclosureRule(
            condition=DisclosureCondition.OPEN,
            reference_id="EVD-001",
        )


def test_npc_knowledge_scope_restriction():
    """NPC 지식 카드는 NPC_ONLY 범위로만 생성할 수 있다."""

    with pytest.raises(ValidationError):
        NPCKnowledgeCard(
            knowledge_id="K-001",
            npc_id="NPC-001",
            knowledge_type=KnowledgeType.OBSERVATION,
            content="비공개 정보",
            disclosure_rule=DisclosureRule(
                condition=DisclosureCondition.OPEN,
            ),
            access_scope="PUBLIC",
        )
