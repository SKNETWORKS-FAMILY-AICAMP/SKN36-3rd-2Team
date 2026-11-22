"""Issue #120 - Django NPC 카드와 RAG 공개 권한 연동 테스트."""

import pytest

from crimescene.api.django_content_client import (
    ApprovedNPCCard,
    ApprovedNPCCards,
)
from crimescene.api.django_npc_card_bridge import (
    select_disclosed_django_cards,
)
from crimescene.scenario.game_progress import create_initial_state
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.access_policy import AccessPolicy

DJANGO_ID = "K-C01-01"
LEGACY_ID = "KC01-E01"
CARD_TEXT = "검증된 공개 진술"


def make_data(
    *,
    disclosed=True,
    unlocked=True,
    mapped=True,
    matching_content=True,
    policy_allowed=True,
):
    state = create_initial_state("test-session").model_copy(
        update={
            "unlocked_characters": ["C01"] if unlocked else [],
            "disclosed_cards": [LEGACY_ID] if disclosed else [],
        }
    )

    django_cards = ApprovedNPCCards(
        character_id="C01",
        cards=[
            ApprovedNPCCard(
                card_id=DJANGO_ID,
                card_type="KNOWLEDGE",
                content=(CARD_TEXT if matching_content else "서로 다른 미검증 진술"),
            )
        ],
    )

    policy = AccessPolicy(
        required_character="C01",
        required_evidence=[],
        required_presentations=[],
        required_flags=[],
        required_ending=None,
        required_topics=[],
        required_disclosed_cards=[],
    )

    evaluator = PolicyEvaluator({"POL-C01-CARD": policy} if policy_allowed else {})

    legacy_cards = [
        {
            "id": LEGACY_ID,
            "case_id": "CASE-001",
            "character_id": "C01",
            "policy_id": "POL-C01-CARD",
            "body": CARD_TEXT,
            "access_scope": "character_only",
            "truth_status": "known_to_character",
            "supersedes": [],
            "stage_priority": 0,
            **policy.model_dump(),
        }
    ]

    return {
        "django_cards": django_cards,
        "state": state,
        "evaluator": evaluator,
        "legacy_cards": legacy_cards,
        "verified_mapping": ({DJANGO_ID: LEGACY_ID} if mapped else {}),
        "active_character_id": "C01",
    }


def test_verified_disclosed_card_is_selected():
    """모든 공개 조건을 충족하면 카드를 선택합니다."""

    result = select_disclosed_django_cards(**make_data())

    assert len(result) == 1
    assert result[0].card_id == DJANGO_ID
    assert result[0].content == CARD_TEXT


@pytest.mark.parametrize(
    "override",
    [
        {"disclosed": False},
        {"unlocked": False},
        {"mapped": False},
        {"matching_content": False},
        {"policy_allowed": False},
    ],
)
def test_unverified_cards_are_blocked(override):
    """공개 조건 중 하나라도 누락되면 차단합니다."""

    result = select_disclosed_django_cards(**make_data(**override))

    assert result == []


def test_wrong_npc_is_rejected():
    """다른 NPC의 응답은 거부합니다."""

    data = make_data()
    data["active_character_id"] = "C02"

    with pytest.raises(ValueError, match="일치하지 않습니다"):
        select_disclosed_django_cards(**data)


def test_duplicate_mapping_is_rejected():
    """여러 Django 카드가 동일한 RAG 카드에 연결되면 거부합니다."""

    data = make_data()
    data["verified_mapping"] = {
        "K-C01-01": LEGACY_ID,
        "K-C01-02": LEGACY_ID,
    }

    with pytest.raises(ValueError, match="동일한 RAG 카드"):
        select_disclosed_django_cards(**data)
