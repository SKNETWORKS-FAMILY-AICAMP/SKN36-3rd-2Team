"""Published evidence-holder retrieval for case001_1120."""

from crimescene.retriever.graph_evidence_search import (
    EvidenceGraphResult,
)
from crimescene.scenario.schemas.game_state import GamePhase

import hashlib
import json

from crimescene.scenario.e26_section_policy import (
    E26_HOLDER_EDGE_ID,
    E26_HOLDER_ID,
    can_access_e26_holder_edge,
)

VERSION = "case001_1120"


def expected_e26_holder_contract():
    source = {
        "evidence_id": "E26",
        "holder": E26_HOLDER_ID,
    }

    source_hash = hashlib.sha256(
        json.dumps(
            source,
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()

    return {
        "edge_id": E26_HOLDER_EDGE_ID,
        "source_id": E26_HOLDER_ID,
        "target_id": "E26",
        "kind": "evidence_holder",
        "relation": "HOLDS_EVIDENCE",
        "source_sha256": source_hash,
    }


def validate_e26_holder_approval(manifest):
    """Require an independent, exact holder approval."""

    key = "approved_e26_holder_edge"

    if key not in manifest:
        return False

    approved = manifest.get("approved_evidence", {})

    if (
        not isinstance(approved, dict)
        or not {"E20", "E26"}.issubset(approved)
        or manifest.get("approved_e26_sections") != ["A"]
        or manifest[key] != expected_e26_holder_contract()
    ):
        raise PermissionError("Invalid E26 holder approval")

    return True


def validate_e26_graph_row(holder, evidence, relation):
    """Reject modified or cross-version E26 graph records."""

    common = {
        "case_id": "CASE-001",
        "content_version": VERSION,
        "runtime_enabled": False,
    }

    expected_holder = {
        **common,
        "entity_id": E26_HOLDER_ID,
        "entity_type": "npc",
    }

    expected_evidence = {
        **common,
        "entity_id": "E26",
        "entity_type": "evidence",
    }

    expected_relation = {
        **common,
        **expected_e26_holder_contract(),
        "contract_approved": False,
    }

    if (
        holder != expected_holder
        or evidence != expected_evidence
        or relation != expected_relation
    ):
        raise PermissionError("E26 holder snapshot mismatch")


HOLDER_QUERY = """
MATCH (holder:Case1120StagingEntity)
      -[r:CASE1120_STAGING_RELATION]->
      (evidence:Case1120StagingEntity)
WHERE r.edge_id IN $edge_ids
RETURN
    properties(holder) AS holder,
    properties(evidence) AS evidence,
    properties(r) AS relation
"""


def search_published_holders(
    *,
    driver,
    state,
    character_id,
    evidence_rules,
    published_holder_ids,
    top_k=10,
):
    if state.content_version != VERSION:
        raise ValueError("Content version mismatch")

    if state.case_id != "CASE-001":
        raise ValueError("Case mismatch")

    if (
        state.phase != GamePhase.INVESTIGATION
        or state.outcome not in (None, "ONGOING")
        or character_id not in state.unlocked_characters
    ):
        return []

    allowed = {
        eid
        for eid in published_holder_ids
        if eid in evidence_rules
        and evidence_rules[eid].holder == character_id
        and eid in state.evidence
        and state.evidence[eid].stage in {"found", "resolved"}
        and eid not in {"E26", "E30"}
    }

    # The list originates from a verified server release.
    if (
        "E26" in published_holder_ids
        and "E26" in evidence_rules
        and evidence_rules["E26"].holder == E26_HOLDER_ID
        and can_access_e26_holder_edge(
            state,
            edge_id=E26_HOLDER_EDGE_ID,
            character_id=character_id,
            section_a_approved=True,
            graph_edge_approved=True,
        )
    ):
        allowed.add("E26")

    if not allowed:
        return []

    with driver.session() as session:
        rows = session.run(
            HOLDER_QUERY,
            edge_ids=[
                f"HOLDER-1120-{eid}"
                for eid in sorted(allowed)
            ],
        ).data()

    results = []
    seen = set()

    for row in rows:
        holder = row["holder"]
        evidence = row["evidence"]
        relation = row["relation"]

        eid = evidence["entity_id"]

        if (
            eid not in allowed
            or holder["entity_id"] != character_id
            or relation["edge_id"] != f"HOLDER-1120-{eid}"
        ):
            raise PermissionError("Graph holder mismatch")

        for item in (holder, evidence, relation):
            if item.get("case_id") != state.case_id:
                raise ValueError("Graph case mismatch")

            version = item.get(
                "content_version",
                item.get("version"),
            )

            if version != VERSION:
                raise ValueError("Graph version mismatch")

        if eid == "E26":
            validate_e26_graph_row(
                holder,
                evidence,
                relation,
            )

        if eid in seen:
            raise ValueError("Duplicate graph holder")

        seen.add(eid)

        results.append(
            EvidenceGraphResult(
                evidence_id=eid,
                holder_id=character_id,
            )
        )

    if seen != allowed:
        raise ValueError("Published graph coverage mismatch")

    return sorted(
        results,
        key=lambda item: item.evidence_id,
    )[:top_k]
