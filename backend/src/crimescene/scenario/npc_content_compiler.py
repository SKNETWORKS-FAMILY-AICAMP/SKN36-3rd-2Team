"""Issue #165 - latest NPC content and disclosure compiler."""

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from crimescene.ingest.npc_knowledge_chunker import (
    build_npc_knowledge_chunks,
)
from crimescene.scenario.schemas.access_policy import AccessPolicy

CONTENT_VERSION = "case001_1120"

EVIDENCE_IDS = {
    f"E{i:02d}"
    for i in range(1, 31)
}

NPC_IDS = {
    f"C{i:02d}"
    for i in range(1, 11)
}

DISCLOSURE_KEY = "\uacf5\uac1c\uc870\uac74"
KNOWLEDGE_BODY = "\ub0b4\uc6a9"
SMALLTALK_BODY = "\uc54c\uace0\uc788\ub294\uc0ac\uc2e4"
TOPIC_KEY = "\ub300\ud654\uc8fc\uc81c"

INITIAL_CONDITIONS = {
    "\ucc98\uc74c\ubd80\ud130",
    "\ud56d\uc0c1",
}

BLOCKED_CONDITIONS = (
    "\uacf5\uac1c \uc548 \ud568",
    "\uc5d4\ub529:",
)

PRESENTATION_PATTERN = re.compile(
    r"P:(E\d{2}(?:\+E\d{2})*)"
    r"(?:\s*\(([23])\ub2e8\uacc4\))?"
)


def classify_disclosure(condition: str) -> dict:
    """Convert only unambiguous disclosure conditions."""

    condition = condition.strip()

    if not condition:
        raise ValueError("Empty disclosure condition")

    if any(
        marker in condition
        for marker in BLOCKED_CONDITIONS
    ):
        return {
            "kind": "ENGINE_ONLY",
            "required_evidence": [],
            "min_stage": None,
        }

    if condition in INITIAL_CONDITIONS:
        return {
            "kind": "INITIAL",
            "required_evidence": [],
            "min_stage": 1,
        }

    matched = PRESENTATION_PATTERN.fullmatch(condition)

    if matched is None:
        return {
            "kind": "MANUAL_REVIEW",
            "required_evidence": [],
            "min_stage": None,
        }

    evidence = matched.group(1).split("+")

    if not set(evidence).issubset(EVIDENCE_IDS):
        raise ValueError("Unknown evidence in disclosure")

    if len(evidence) != len(set(evidence)):
        raise ValueError("Duplicate disclosure evidence")

    stage = matched.group(2)

    return {
        "kind": (
            "PRESENTATION_STAGE"
            if stage
            else "PRESENTATION"
        ),
        "required_evidence": evidence,
        "min_stage": int(stage) if stage else None,
    }


def compile_npc_card(row: dict) -> dict:
    npc_id = row["npc_id"].strip()
    card_id = row["card_id"].strip()

    if npc_id not in NPC_IDS:
        raise ValueError("Unknown NPC")

    if not re.fullmatch(
        rf"K-{npc_id}-(?:\d{{2}}|S\d{{2}})",
        card_id,
    ):
        raise ValueError("Invalid NPC card ID")

    is_smalltalk = card_id.rsplit("-", 1)[-1].startswith("S")

    body_key = (
        SMALLTALK_BODY
        if is_smalltalk
        else KNOWLEDGE_BODY
    )

    body = row[body_key].strip()
    condition = row[DISCLOSURE_KEY].strip()

    if not body:
        raise ValueError("Empty card body")

    classification = classify_disclosure(condition)

    evidence_ids = classification["required_evidence"]

    candidate_policy = AccessPolicy(
        required_evidence=evidence_ids,
        required_presentations=[
            f"{npc_id}:{eid}"
            for eid in evidence_ids
        ],
        required_flags=[],
        required_ending=None,
        required_topics=[],
        required_disclosed_cards=[],
        required_character=npc_id,
        required_npc_stage=classification["min_stage"],
    )

    policy_id = f"POL-1120-{card_id}"

    point_id = str(uuid5(
        NAMESPACE_URL,
        f"crimescene/{CONTENT_VERSION}/npc/{card_id}",
    ))

    # Draft-only protection: not a publishable policy.
    staging_policy = candidate_policy.model_copy(
        update={
            "required_flags": [
                "INTERNAL_DRAFT_NOT_PUBLISHED",
            ],
        },
    )

    rag_card = {
        "id": card_id,
        "case_id": "CASE-001",
        "character_id": npc_id,
        "policy_id": policy_id,
        "point_id": point_id,
        "body": body,
        "search_text": (
            f"{row.get(TOPIC_KEY, '')} {body}".strip()
        ),
        "family": (
            "npc_smalltalk"
            if is_smalltalk
            else "npc_knowledge"
        ),
        "access_scope": "character_only",
        "truth_status": "character_claim",
        "incident_year": None,
        "content_hash": hashlib.sha256(
            body.encode("utf-8")
        ).hexdigest(),
        "supersedes": [],
        "stage_priority": 0,
        "effects": {"find": []},
        **staging_policy.model_dump(mode="json"),
    }

    return {
        "card_id": card_id,
        "character_id": npc_id,
        "content_version": CONTENT_VERSION,
        "classification": classification,
        "source_condition": condition,
        "contract_approved": False,
        "runtime_enabled": False,
        "candidate_policy": (
            candidate_policy.model_dump(mode="json")
            if classification["kind"] not in {
                "MANUAL_REVIEW",
                "ENGINE_ONLY",
            }
            else None
        ),
        "staging_card": rag_card,
        "staging_policy": staging_policy.model_dump(
            mode="json"
        ),
    }


def compile_npc_catalog(catalog: dict) -> dict:
    if catalog.get("content_version") != CONTENT_VERSION:
        raise ValueError("Content version mismatch")

    if catalog.get("status") != "DRAFT":
        raise ValueError("Expected draft catalog")

    if catalog.get("runtime_enabled") is not False:
        raise ValueError("Expected disabled runtime")

    cards = [
        compile_npc_card(row)
        for row in catalog["npc_cards"]
    ]

    ids = {card["card_id"] for card in cards}

    if len(cards) != 140 or len(ids) != 140:
        raise ValueError("NPC card count mismatch")

    policies = {
        card["staging_card"]["policy_id"]:
        card["staging_policy"]
        for card in cards
    }

    # Validate compatibility with the existing RAG chunker.
    chunks = build_npc_knowledge_chunks(
        [card["staging_card"] for card in cards],
        expected_case_id="CASE-001",
        valid_policy_ids=set(policies),
    )

    if len(chunks) != len(cards):
        raise ValueError("NPC chunk count mismatch")

    return {
        "content_version": CONTENT_VERSION,
        "status": "DRAFT",
        "runtime_enabled": False,
        "cards": cards,
        "policy_count": len(policies),
        "chunk_count": len(chunks),
        "classification_counts": dict(Counter(
            card["classification"]["kind"]
            for card in cards
        )),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--catalog",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
    )
    args = parser.parse_args()

    catalog = json.loads(
        args.catalog.read_text(encoding="utf-8-sig")
    )

    result = compile_npc_catalog(catalog)

    output = args.output.resolve()

    if ".local" not in output.parts:
        raise ValueError("Draft output must remain local")

    output.parent.mkdir(parents=True, exist_ok=True)

    with output.open("x", encoding="utf-8") as f:
        json.dump(
            result,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print("NPC CARDS:", len(result["cards"]))
    print("NPC POLICIES:", result["policy_count"])
    print("NPC RAG CHUNKS:", result["chunk_count"])

    for kind, count in sorted(
        result["classification_counts"].items()
    ):
        print(kind, count)

    print("RUNTIME ENABLED:", result["runtime_enabled"])
    print("NPC CONTENT COMPILATION COMPLETE")


if __name__ == "__main__":
    main()
