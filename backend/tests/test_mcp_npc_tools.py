
"""Issue #134 - Django 승인 및 NPC 접근 정책 검증."""

import pytest
from mcp import Client

from crimescene.api.django_content_client import (
    ApprovedNPCCard,
    ApprovedNPCCards,
    ContentServiceError,
)
from crimescene.mcp.context import BoundMCPContext
from crimescene.mcp.server import create_readonly_mcp_server
from crimescene.scenario.game_progress import (
    create_initial_state,
    transition_phase,
)
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import GamePhase


@pytest.fixture
def anyio_backend():
    return "asyncio"


def make_policy(*, required_evidence=None):
    return AccessPolicy(
        required_evidence=required_evidence or [],
        required_presentations=[],
        required_flags=[],
        required_ending=None,
        required_topics=[],
        required_disclosed_cards=[],
        required_character="C01",
    )


def make_card(card_id, content, policy_id, policy):
    return {
        **policy.model_dump(),
        "id": card_id,
        "case_id": "CASE-001",
        "character_id": "C01",
        "policy_id": policy_id,
        "body": content,
        "access_scope": "character_only",
        "truth_status": "character_claim",
        "supersedes": [],
        "stage_priority": 1,
    }


class FakeDjango:
    def __init__(self, cards, *, fail=False):
        self.cards = cards
        self.fail = fail

    def get_approved_npc_cards(self, case_id, character_id):
        if self.fail:
            raise ContentServiceError("Django unavailable")

        return ApprovedNPCCards(
            character_id=character_id,
            cards=self.cards,
        )


def make_server(*, approved_secret=True, django_fail=False, selected=True):
    state = transition_phase(
        create_initial_state("mcp-npc-test"),
        GamePhase.INVESTIGATION,
    )

    open_policy = make_policy()
    secret_policy = make_policy(required_evidence=["E02"])

    cards = [
        make_card(
            "K-C01-01",
            "게임 내 공개 가능한 지식",
            "POL-OPEN",
            open_policy,
        ),
        make_card(
            "K-C01-02",
            "아직 접근할 수 없는 비공개 지식",
            "POL-SECRET",
            secret_policy,
        ),
    ]

    approved = [
        ApprovedNPCCard(
            card_id="K-C01-01",
            card_type="KNOWLEDGE",
            content="게임 내 공개 가능한 지식",
        ),
    ]

    if approved_secret:
        approved.append(
            ApprovedNPCCard(
                card_id="K-C01-02",
                card_type="KNOWLEDGE",
                content="아직 접근할 수 없는 비공개 지식",
            )
        )

    context = BoundMCPContext.from_owned_game_state(
        state=state,
        load_state=lambda _: state,
        active_character_id="C01" if selected else None,
    )

    server = create_readonly_mcp_server(
        context=context,
        evidence_rules={
            "E01": EvidenceRule(
                name="증거",
                score=2,
                holder="C01",
                prerequisites=[],
                presentation=[],
                q=[],
            )
        },
        npc_cards=cards,
        evaluator=PolicyEvaluator(
            {
                "POL-OPEN": open_policy,
                "POL-SECRET": secret_policy,
            }
        ),
        django_client=FakeDjango(approved, fail=django_fail),
    )

    return server


@pytest.mark.anyio
async def test_npc_knowledge_uses_both_approval_gates():
    async with Client(make_server()) as client:
        result = await client.call_tool("get_npc_knowledge", {})

    assert not result.is_error
    assert result.structured_content is not None

    data = result.structured_content

    assert data["character_id"] == "C01"
    assert len(data["items"]) == 1
    assert data["items"][0]["card_id"] == "K-C01-01"
    assert "비공개 지식" not in str(data)


@pytest.mark.anyio
async def test_npc_knowledge_requires_django_approval():
    server = make_server(approved_secret=False)

    async with Client(server) as client:
        result = await client.call_tool("get_npc_knowledge", {})

    assert not result.is_error
    assert len(result.structured_content["items"]) == 1
    assert result.structured_content["items"][0]["card_id"] == "K-C01-01"


@pytest.mark.anyio
async def test_npc_knowledge_without_selected_npc_rejected():
    server = make_server(selected=False)

    async with Client(server) as client:
        result = await client.call_tool("get_npc_knowledge", {})

    assert result.is_error
    assert result.structured_content is None


@pytest.mark.anyio
async def test_npc_knowledge_django_failure_closed():
    server = make_server(django_fail=True)

    async with Client(server) as client:
        result = await client.call_tool("get_npc_knowledge", {})

    assert result.is_error
    assert result.structured_content is None
