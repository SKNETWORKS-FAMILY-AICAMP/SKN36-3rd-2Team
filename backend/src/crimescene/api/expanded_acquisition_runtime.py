"""Release-bound evidence acquisition contracts."""

import hashlib
import json

from crimescene.scenario.acquisition_policy import AcquisitionPolicy

VERSION = "case001_1120"


LEGACY_PUBLICATION_IDS = frozenset(
    {
        "E01",
        "E02",
        "E03",
        "E04",
        "E05",
        "E06",
        "E08",
        "E09",
        "E10",
    }
)


def build_legacy_acquisition_candidate(eid, item):
    """Convert reviewed legacy evidence to an explicit acquisition route."""
    if eid not in LEGACY_PUBLICATION_IDS:
        raise PermissionError("Legacy evidence not reviewed")

    if item["origin"] != "case001_v7_1":
        raise ValueError("Legacy source mismatch")

    rule = item["legacy_rule"]

    policy = AcquisitionPolicy.model_validate(
        {
            "evidence_id": eid,
            "routes": [
                {
                    "route_id": f"{eid}-LEGACY",
                    "chapter": "CH01",
                    "action_flag": f"ACT_LEGACY_{eid}_INSPECTED",
                    "policy": {
                        "required_evidence": list(rule["prerequisites"]),
                        "required_presentations": list(rule["presentation"]),
                        "required_flags": [],
                        "required_ending": None,
                        "required_topics": [],
                        "required_disclosed_cards": [],
                        "required_character": rule["holder"],
                        "required_npc_stage": None,
                    },
                }
            ],
        }
    )

    return policy.model_dump(mode="json")


def load_published_acquisition_policies(
    *,
    manifest,
    catalog_path,
):
    if manifest.get("content_version") != VERSION:
        raise ValueError("Content version mismatch")

    actual_hash = hashlib.sha256(catalog_path.read_bytes()).hexdigest()

    if actual_hash != manifest.get("catalog_sha256"):
        raise ValueError("Acquisition catalog hash mismatch")

    catalog = json.loads(catalog_path.read_text(encoding="utf-8-sig"))

    approved = manifest["approved_evidence"]

    validate_e26_release_contract(manifest)

    contracts = manifest["approved_acquisition_routes"]

    if set(contracts) != set(approved):
        raise ValueError("Acquisition coverage mismatch")

    policies = {}

    for eid, contract in sorted(contracts.items()):
        item = catalog["evidence"][eid]

        if eid in LEGACY_PUBLICATION_IDS:
            candidate = build_legacy_acquisition_candidate(eid, item)
        else:
            candidate = item["acquisition_policy_candidate"]

        source_routes = {item["route_id"]: item for item in candidate["routes"]}

        if contract["evidence_id"] != eid:
            raise ValueError("Evidence ID mismatch")

        for route in contract["routes"]:
            if source_routes.get(route["route_id"]) != route:
                raise ValueError("Acquisition route changed")

            access = route["policy"]

            dependencies = set(access["required_evidence"])

            dependencies.update(
                value.split(":")[-1] for value in access["required_presentations"]
            )

            if not dependencies.issubset(approved):
                raise PermissionError("Unpublished dependency")

        policies[eid] = AcquisitionPolicy.model_validate(contract)

    return policies

def validate_e26_release_contract(manifest):
    """Require an explicit A-only publication contract."""

    approved = manifest["approved_evidence"]
    sections = manifest.get("approved_e26_sections", [])
    actions = manifest.get("approved_investigation_actions", {})

    if not isinstance(approved, dict):
        raise ValueError("Invalid evidence approval")

    if not isinstance(actions, dict):
        raise ValueError("Invalid investigation approval")

    e26_actions = {
        action_id
        for action_id, contract in actions.items()
        if isinstance(contract, dict)
        and contract.get("evidence_id") == "E26"
    }

    if "E26" not in approved:
        if sections != [] or e26_actions:
            raise PermissionError("Unpublished E26 contract")

        return False

    if sections != ["A"]:
        raise PermissionError("E26 requires A-only approval")

    contract = approved["E26"]

    if (
        not isinstance(contract, dict)
        or contract.get("score") != 3
        or contract.get("required_evidence") != ["E20"]
        or "E20" not in approved
    ):
        raise PermissionError("Invalid E26 evidence contract")

    acquisition = manifest["approved_acquisition_routes"].get("E26")

    policy = AcquisitionPolicy.model_validate(acquisition)

    if policy.evidence_id != "E26" or len(policy.routes) != 1:
        raise PermissionError("Invalid E26 acquisition contract")

    route = policy.routes[0]

    if (
        route.route_id != "E26-A"
        or route.chapter != "CH03"
        or route.action_flag != "ACT_AUDIT_LOG_ACCESS_VERIFIED"
        or route.policy.required_evidence != ["E20"]
        or route.policy.required_character is not None
    ):
        raise PermissionError("Invalid E26-A route")

    if e26_actions != {"inspect-e26-a"}:
        raise PermissionError("Unexpected E26 investigation route")

    action = actions["inspect-e26-a"]

    if (
        action.get("scene_id") != "SC-0306"
        or action.get("chapter") != "CH03"
        or action.get("route_ids") != ["E26-A"]
        or action.get("character_id") is not None
    ):
        raise PermissionError("Invalid E26 investigation contract")

    return True
