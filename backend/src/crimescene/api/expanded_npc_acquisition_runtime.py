"""Configure release-bound NPC evidence acquisition."""

from crimescene.trigger.published_npc_acquisition import (
    apply_published_npc_acquisition,
)


def configure_published_npc_acquisitions(
    *,
    app,
    manifest,
    source_dir=None,
):
    if manifest["content_version"] != "case001_1120":
        raise ValueError("Invalid content version")

    if manifest["scope"] != "LOCAL_INTEGRATION_TEST":
        raise ValueError("Invalid release scope")

    contracts = manifest.get(
        "approved_npc_acquisitions", {}
    )

    if not isinstance(contracts, dict):
        raise TypeError("Invalid NPC acquisition contracts")

    approved_cards = manifest["approved_npc_cards"]
    approved_evidence = manifest["approved_evidence"]

    resources = app.state.dialogue_resources
    django = app.state.django_content_client
    policies = app.state.approved_acquisition_routes

    if resources.content_version != "case001_1120":
        raise ValueError("Resource version mismatch")

    for route_id, contract in contracts.items():
        cid = contract["card_id"]
        eid = contract["evidence_id"]
        npc = contract["character_id"]

        if (
            cid not in approved_cards
            or eid not in approved_evidence
            or eid not in policies
            or eid in {"E26", "E27", "E29", "E30"}
        ):
            raise PermissionError("Unpublished NPC acquisition")

        if approved_cards[cid]["character_id"] != npc:
            raise PermissionError("NPC card ownership mismatch")

        routes = [
            route for route in policies[eid].routes
            if route.route_id == route_id
        ]

        if len(routes) != 1:
            raise ValueError("Invalid NPC acquisition route")

        route = routes[0]

        if (
            route.policy.required_character != npc
            or route.chapter != contract["chapter"]
            or route.action_flag != contract["action_flag"]
            or contract.get("requires_grounded_reply") is not True
        ):
            raise ValueError("NPC acquisition contract mismatch")

    def acquire(state, turn):
        return apply_published_npc_acquisition(
            state=state,
            turn=turn,
            contracts=contracts,
            policies=policies,
            resources=resources,
            django=django,
            approved_evidence=approved_evidence,
        )

    stage_rules = load_published_presentation_rules(
        manifest=manifest,
        source_dir=source_dir,
    )

    app.state.presentation_stage_rules = stage_rules
    app.state.published_npc_acquisition = acquire

    print("APPROVED NPC ACQUISITIONS:", sorted(contracts))

    return acquire


def load_published_presentation_rules(
    *,
    manifest,
    source_dir,
):
    import csv
    import hashlib
    from pathlib import Path

    from crimescene.trigger.expanded_dialogue import (
        compile_dialogue_index,
    )
    from crimescene.trigger.npc_stage_rules import (
        load_approved_stage_rules,
    )

    approvals = manifest.get(
        "approved_presentation_stage_rules", {}
    )

    if not approvals:
        return ()

    if source_dir is None:
        raise ValueError("Dialogue source directory required")

    path = Path(source_dir) / "09_NPC_DIALOGUE_TRIGGERS.csv"

    digest = hashlib.sha256(
        path.read_bytes()
    ).hexdigest()

    if digest != manifest["dialogue_source_sha256"]:
        raise ValueError("Dialogue source hash mismatch")

    with path.open(
        encoding="utf-8-sig",
        newline="",
    ) as file:
        index = compile_dialogue_index(
            list(csv.DictReader(file))
        )

    rules = load_approved_stage_rules(
        index,
        approvals,
    )

    published = set(manifest["approved_evidence"])

    for rule in rules:
        if not rule.evidence_ids.issubset(published):
            raise PermissionError("Unpublished stage dependency")

        if rule.evidence_ids.intersection({"E26", "E30"}):
            raise PermissionError("Protected stage dependency")

    print("PRESENTATION STAGE RULES:", len(rules))

    return rules
