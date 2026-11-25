"""Release-bound investigation runtime configuration."""

from crimescene.api.expanded_acquisition_runtime import (
    load_published_acquisition_policies,
    validate_e26_release_contract,
)
from crimescene.api.expanded_release_runtime import (
    load_release_manifest,
)
from crimescene.api.investigation_http import ACTION_CANDIDATES


def validate_e26_followup_contract(manifest):
    approved = manifest["approved_evidence"]
    actions = manifest["approved_investigation_actions"]

    for eid, action_id in (
        ("E27", "inspect-e27-a"),
        ("E29", "inspect-e29-a"),
    ):
        matching_actions = {
            key for key, item in actions.items()
            if item.get("evidence_id") == eid
        }

        if eid not in approved:
            if matching_actions:
                raise PermissionError(
                    "Unpublished follow-up evidence"
                )
            continue

        if (
            manifest.get("approved_e26_sections") != ["A"]
            or manifest.get("approved_e26_inference") is not True
            or not {"E20", "E26"}.issubset(approved)
            or matching_actions != {action_id}
        ):
            raise PermissionError(
                "Follow-up evidence approval unavailable"
            )

        candidate = ACTION_CANDIDATES[action_id]
        contract = actions[action_id]
        evidence = approved[eid]

        if (
            evidence.get("score") != 3
            or set(evidence.get("required_evidence", []))
            != candidate.required_evidence
            or not candidate.required_evidence.issubset(approved)
            or contract.get("scene_id") != candidate.scene_id
            or contract.get("chapter") != candidate.chapter
            or contract.get("route_ids") != sorted(candidate.route_ids)
            or set(contract.get("required_flags", []))
            != candidate.required_flags
            or contract.get("character_id") is not None
        ):
            raise PermissionError(
                "Invalid follow-up evidence contract"
            )


def configure_published_investigations(
    *,
    app,
    token,
    catalog_path,
    release_version,
):
    manifest = load_release_manifest(
        token,
        release_version,
    )

    if manifest["content_version"] != "case001_1120":
        raise ValueError("Invalid content version")

    policies = load_published_acquisition_policies(
        manifest=manifest,
        catalog_path=catalog_path,
    )

    validate_e26_followup_contract(manifest)

    actions = manifest["approved_investigation_actions"]

    if not actions:
        raise ValueError("No published investigation actions")

    for action_id, contract in actions.items():
        action = ACTION_CANDIDATES.get(action_id)

        if action is None:
            raise ValueError("Unknown investigation action")

        if (
            action.scene_id != contract["scene_id"]
            or action.chapter != contract["chapter"]
            or action.evidence_id != contract["evidence_id"]
            or action.required_character != contract.get("character_id")
        ):
            raise ValueError("Investigation contract mismatch")

        published_route_ids = contract.get("route_ids")

        if (
            published_route_ids is not None
            and frozenset(published_route_ids) != action.route_ids
        ):
            raise ValueError("Published route IDs mismatch")

        if (
            action.required_flags
            != frozenset(contract.get("required_flags", []))
        ):
            raise ValueError("Investigation flags mismatch")

        policy = policies.get(action.evidence_id)

        if policy is None:
            raise ValueError("Missing acquisition policy")

        valid_routes = {
            route.route_id
            for route in policy.routes
            if route.chapter == action.chapter
            and route.action_flag == action.action_flag
            and route.policy.required_character == action.required_character
        }

        if not action.route_ids.issubset(valid_routes):
            raise ValueError("Investigation route mismatch")

    app.state.e26_section_a_approved = validate_e26_release_contract(manifest)
    app.state.approved_acquisition_routes = policies
    app.state.approved_investigation_actions = frozenset(actions)
    app.state.investigation_release_version = release_version

    print("INVESTIGATION RELEASE:", release_version)
    print("ACQUISITION POLICIES:", len(policies))
    print("APPROVED ACTIONS:", sorted(actions))

    return manifest
