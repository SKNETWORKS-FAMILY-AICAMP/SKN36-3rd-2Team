"""Collect evidence from verified NPC dialogue."""

from crimescene.scenario.acquisition_policy import (
    AcquisitionPolicy,
    allows_acquisition,
)
from crimescene.scenario.evidence_collection import collect_evidence
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.game_state import GamePhase, GameState


def apply_published_npc_acquisition(
    *,
    state,
    turn,
    contracts,
    policies,
    resources,
    django,
    approved_evidence,
):
    if (
        state.case_id != "CASE-001"
        or state.content_version != "case001_1120"
        or state.phase != GamePhase.INVESTIGATION
        or state.outcome not in (None, "ONGOING")
        or turn.character_id not in state.unlocked_characters
        or turn.reply.grounded is not True
    ):
        return state

    updated = state

    for route_id, contract in sorted(contracts.items()):
        npc = contract["character_id"]
        eid = contract["evidence_id"]
        cid = contract["card_id"]

        if (
            turn.character_id != npc
            or cid not in turn.reply.source_ids
            or cid not in updated.disclosed_cards
            or updated.current_chapter != contract["chapter"]
            or eid in updated.evidence
        ):
            continue

        if eid in {"E26", "E27", "E29", "E30"}:
            raise PermissionError("Protected evidence")

        if contract.get("requires_grounded_reply") is not True:
            raise ValueError("Invalid dialogue contract")

        if eid not in approved_evidence:
            raise PermissionError("Unpublished evidence")

        card = next(
            (
                item for item in resources.npc_cards
                if item["id"] == cid
                and item["character_id"] == npc
            ),
            None,
        )

        if card is None:
            raise PermissionError("NPC source unavailable")

        if not resources.evaluator.is_allowed(
            card["policy_id"],
            updated,
            active_character_id=npc,
        ):
            raise PermissionError("NPC source not authorized")

        policy = policies[eid]

        route = next(
            (
                item for item in policy.routes
                if item.route_id == route_id
            ),
            None,
        )

        if (
            route is None
            or route.policy.required_character != npc
            or route.action_flag != contract["action_flag"]
            or route.chapter != contract["chapter"]
        ):
            raise ValueError("NPC acquisition route mismatch")

        selected_policy = AcquisitionPolicy(
            evidence_id=eid,
            routes=[route],
        )

        # Stage the server-verified dialogue flag.
        staged = GameState.model_validate({
            **updated.model_dump(),
            "flags": sorted(
                set(updated.flags) | {route.action_flag}
            ),
        })

        if not allows_acquisition(
            selected_policy,
            staged,
            active_character_id=npc,
        ):
            continue

        remote = django.get_approved_npc_cards(
            state.case_id,
            npc,
        )

        if remote.character_id != npc:
            raise PermissionError("NPC ownership mismatch")

        if not any(
            item.card_id == cid
            and item.content == card["body"]
            and item.card_type == "KNOWLEDGE"
            for item in remote.cards
        ):
            raise PermissionError("NPC publication revoked")

        requirements = django.get_evidence_requirements(
            state.case_id,
            eid,
        )

        expected = set(
            approved_evidence[eid]["required_evidence"]
        )

        if (
            requirements.evidence_id != eid
            or set(requirements.prerequisites) != expected
        ):
            raise ValueError("Evidence publication mismatch")

        acquired = {
            key for key, item in updated.evidence.items()
            if item.stage in {"found", "resolved"}
        }

        if not expected.issubset(acquired):
            continue

        result = collect_evidence(
            state=staged,
            evidence_id=eid,
            evidence_rules=resources.evidence_rules,
            acquisition_policy_ids={},
            evaluator=PolicyEvaluator({}),
            active_character_id=npc,
            approved_routes={eid: selected_policy},
        )

        updated = result.state

    return updated
