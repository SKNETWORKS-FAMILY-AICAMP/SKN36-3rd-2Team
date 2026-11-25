"""Issue #165 - isolated CASE-001 1120 RAG dataset."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from crimescene.db.ingest_integrity import validate_qdrant_records
from crimescene.ingest.case001_dataset import (
    load_case001_hybrid_records,
    load_npc_cards,
)
from crimescene.ingest.chunking_config import ChunkingConfig, ChunkingMode
from crimescene.scenario.loaders.access_policy_loader import (
    load_access_policies,
)
from crimescene.scenario.loaders.document_loader import (
    load_player_documents,
)
from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.scenario.schemas.document import PlayerDocument

VERSION = "case001_1120"
CASE_ID = "CASE-001"
DRAFT_FLAG = "INTERNAL_DRAFT_NOT_PUBLISHED"
COLLECTION = "case001_rag_1120_staging"

LEGACY_IDS = frozenset(
    f"E{i:02d}" for i in range(1, 11)
)

ALL_IDS = frozenset(
    f"E{i:02d}" for i in range(1, 31)
)

BLOCKED_EVIDENCE = frozenset({"E26", "E30"})


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def point_id(source_id):
    return str(uuid5(
        NAMESPACE_URL,
        f"crimescene/{VERSION}/{source_id}",
    ))


def read_json(path):
    return json.loads(
        path.read_text(encoding="utf-8-sig")
    )


def write_verified(path, text):
    """Never overwrite different existing content."""

    if path.exists():
        if path.read_text(encoding="utf-8-sig") != text:
            raise ValueError(f"Existing file mismatch: {path.name}")

        return

    with path.open("x", encoding="utf-8") as file:
        file.write(text)


def draft_policy(policy):
    data = policy.model_dump(mode="json")

    data["required_flags"] = sorted(
        set(data["required_flags"]) | {DRAFT_FLAG}
    )

    return AccessPolicy.model_validate(data)


def evidence_policy(eid):
    return AccessPolicy(
        required_evidence=[eid],
        required_presentations=[],
        required_flags=[DRAFT_FLAG],
        required_ending=None,
        required_topics=[],
        required_disclosed_cards=[],
        required_character=None,
    )


def make_extended_document(eid, item):
    row = item["source"]

    if row["evidence_id"] != eid:
        raise ValueError("Evidence source mismatch")

    if row["access_scope"] != "UNLOCKED_ONLY":
        raise ValueError("Invalid evidence scope")

    title = row["title"].strip()
    body = row["finding_public"].strip()

    if not title or not body:
        raise ValueError(f"Missing public finding: {eid}")

    doc_id = f"DOC-1120-{eid}"
    policy_id = f"POL-1120-DOC-{eid}"

    document = PlayerDocument(
        doc_id=doc_id,
        case_id=CASE_ID,
        title=title,
        body=body,
        family="evidence",
        access_scope="collected_evidence",
        truth_status="documented_in_game",
        source_evidence_ids=[eid],
        known_by_character_ids=[],
        source_doc_ids=[],
        required_evidence=[eid],
        required_presentations=[],
        required_flags=[DRAFT_FLAG],
        required_ending=None,
        protected_fact_ids=[],
        incident_year=None,
        incident_years=[],
        source_refs=[
            f"05_EVIDENCE_E11_E30.csv:{eid}",
        ],
        record_id=f"REC-1120-{eid}",
        point_id=point_id(doc_id),
        policy_id=policy_id,
        state_version=VERSION,
        content_version=VERSION,
        build_id=f"{VERSION}_staging",
        content_hash=sha256(body),
        search_text=f"{title}\n{body}",
    )

    return document, evidence_policy(eid)


def find_legacy_data(root):
    paths = [
        path.parent
        for path in root.rglob("player_documents.jsonl")
        if (path.parent / "access_policies.json").is_file()
    ]

    if len(paths) != 1:
        raise ValueError("Legacy document directory is ambiguous")

    return paths[0]


def build_dataset(
    *,
    catalog_path,
    npc_catalog_path,
    legacy_root,
    output,
):
    catalog = read_json(catalog_path)
    npc_catalog = read_json(npc_catalog_path)

    for source in (catalog, npc_catalog):
        if (
            source["content_version"] != VERSION
            or source["runtime_enabled"] is not False
        ):
            raise ValueError("Unexpected source version")

    evidence = catalog["evidence"]

    if set(evidence) != ALL_IDS:
        raise ValueError("Expected exactly 30 evidence IDs")

    documents = []
    cards = []
    policies = {}
    excluded = Counter()

    # Legacy evidence documents remain unapproved candidates.
    data_dir = find_legacy_data(legacy_root)

    legacy_policies = load_access_policies(
        data_dir / "access_policies.json"
    )

    legacy_documents = load_player_documents(
        data_dir / "player_documents.jsonl"
    )

    for doc in legacy_documents:
        source_ids = set(doc.source_evidence_ids)

        if (
            doc.family != "evidence"
            or doc.access_scope != "collected_evidence"
            or not source_ids
            or not source_ids.issubset(LEGACY_IDS)
            or doc.protected_fact_ids
            or doc.required_ending is not None
        ):
            excluded["legacy_documents"] += 1
            continue

        policy = legacy_policies[doc.policy_id]

        if policy.required_ending is not None:
            excluded["legacy_documents"] += 1
            continue

        new_policy_id = f"POL-1120-LEGACY-{doc.doc_id}"

        policy_data = policy.model_dump(mode="json")
        policy_data["required_evidence"] = sorted(
            set(policy.required_evidence) | source_ids
        )

        new_policy = draft_policy(
            AccessPolicy.model_validate(policy_data)
        )

        data = doc.model_dump(mode="json")

        data.update({
            "point_id": point_id(doc.doc_id),
            "policy_id": new_policy_id,
            "required_evidence": sorted(
                set(doc.required_evidence) | source_ids
            ),
            "required_flags": sorted(
                set(doc.required_flags) | {DRAFT_FLAG}
            ),
            "content_version": VERSION,
            "state_version": VERSION,
            "build_id": f"{VERSION}_staging",
            "content_hash": sha256(doc.body),
        })

        documents.append(PlayerDocument.model_validate(data))
        policies[new_policy_id] = new_policy

    # Only the explicitly public finding field is indexed.
    for eid in sorted(ALL_IDS - LEGACY_IDS):
        if eid in BLOCKED_EVIDENCE:
            excluded["protected_evidence"] += 1
            continue

        doc, policy = make_extended_document(
            eid,
            evidence[eid],
        )

        documents.append(doc)
        policies[doc.policy_id] = policy

    raw_cards = npc_catalog["cards"]

    if isinstance(raw_cards, dict):
        raw_cards = list(raw_cards.values())

    if len(raw_cards) != 140:
        raise ValueError("Expected 140 NPC cards")

    for item in raw_cards:
        if item.get("candidate_policy") is None:
            excluded["unresolved_npc_cards"] += 1
            continue

        card = dict(item["staging_card"])

        policy = draft_policy(
            AccessPolicy.model_validate(
                item["staging_policy"]
            )
        )

        if "E30" in policy.required_evidence or any(
            value.endswith(":E30")
            for value in policy.required_presentations
        ):
            excluded["protected_npc_cards"] += 1
            continue

        if policy.required_character != card["character_id"]:
            raise ValueError("NPC ownership mismatch")

        card["required_flags"] = sorted(
            set(card.get("required_flags", []))
            | {DRAFT_FLAG}
        )

        card["point_id"] = point_id(card["id"])
        card["content_hash"] = sha256(card["body"])

        if card["policy_id"] in policies:
            raise ValueError("Duplicate policy ID")

        cards.append(card)
        policies[card["policy_id"]] = policy

    if not documents or not cards:
        raise ValueError("Empty staging dataset")

    if len({doc.doc_id for doc in documents}) != len(documents):
        raise ValueError("Duplicate document ID")

    if len({card["id"] for card in cards}) != len(cards):
        raise ValueError("Duplicate NPC card ID")

    if not all(
        DRAFT_FLAG in policy.required_flags
        for policy in policies.values()
    ):
        raise ValueError("Missing staging denial flag")

    output.mkdir(parents=True, exist_ok=True)

    write_verified(
        output / "player_documents.jsonl",
        "".join(
            doc.model_dump_json() + "\n"
            for doc in documents
        ),
    )

    write_verified(
        output / "npc_knowledge_cards.jsonl",
        "".join(
            json.dumps(card, ensure_ascii=False) + "\n"
            for card in cards
        ),
    )

    write_verified(
        output / "access_policies.json",
        json.dumps(
            {
                key: value.model_dump(mode="json")
                for key, value in policies.items()
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n",
    )

    config = ChunkingConfig(
        mode=ChunkingMode.FIXED,
        max_chunk_chars=800,
        overlap_chars=80,
    )

    records = load_case001_hybrid_records(
        output,
        config=config,
    )

    report = validate_qdrant_records(
        records,
        document_ids={doc.doc_id for doc in documents},
        npc_card_ids={card["id"] for card in cards},
        valid_policy_ids=set(policies),
    )

    if report.source_count != len(documents) + len(cards):
        raise ValueError("Source count mismatch")

    coverage = sorted({
        eid
        for doc in documents
        for eid in doc.source_evidence_ids
    })

    manifest = {
        "case_id": CASE_ID,
        "content_version": VERSION,
        "status": "STAGING_ONLY",
        "runtime_enabled": False,
        "collection": COLLECTION,
        "documents": len(documents),
        "npc_cards": len(cards),
        "policies": len(policies),
        "chunks": report.point_count,
        "evidence_coverage": coverage,
        "excluded": dict(excluded),
        "chunking": config.model_dump(mode="json"),
        "file_hashes": {
            name: hashlib.sha256(
                (output / name).read_bytes()
            ).hexdigest()
            for name in (
                "player_documents.jsonl",
                "npc_knowledge_cards.jsonl",
                "access_policies.json",
            )
        },
    }

    write_verified(
        output / "manifest.json",
        json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
        ) + "\n",
    )

    print(json.dumps(manifest, indent=2))
    print("EXPANDED RAG DATASET COMPLETE")


def load_verified_dataset(output, *, expected_collection=COLLECTION):
    manifest = read_json(output / "manifest.json")

    if (
        manifest["status"] != "STAGING_ONLY"
        or manifest["content_version"] != VERSION
        or manifest["collection"] != expected_collection
        or manifest["runtime_enabled"] is not False
    ):
        raise ValueError("Invalid staging manifest")

    expected_files = {
        "player_documents.jsonl",
        "npc_knowledge_cards.jsonl",
        "access_policies.json",
    }

    if set(manifest["file_hashes"]) != expected_files:
        raise ValueError("Invalid manifest file set")

    for name, expected in manifest["file_hashes"].items():
        actual = hashlib.sha256(
            (output / name).read_bytes()
        ).hexdigest()

        if actual != expected:
            raise ValueError("Dataset hash mismatch")

    policies = load_access_policies(
        output / "access_policies.json"
    )

    if not all(
        DRAFT_FLAG in policy.required_flags
        for policy in policies.values()
    ):
        raise ValueError("Unsafe staging policy")

    records = load_case001_hybrid_records(
        output,
        config=ChunkingConfig.model_validate(
            manifest["chunking"]
        ),
    )

    docs = load_player_documents(
        output / "player_documents.jsonl"
    )

    cards = load_npc_cards(
        output / "npc_knowledge_cards.jsonl"
    )

    if (
        len(records) != manifest["chunks"]
        or len(docs) != manifest["documents"]
        or len(cards) != manifest["npc_cards"]
        or len(policies) != manifest["policies"]
    ):
        raise ValueError("Dataset count mismatch")

    return records, docs, cards, policies


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--npc-catalog", type=Path, required=True)
    parser.add_argument("--legacy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()

    build_dataset(
        catalog_path=args.catalog,
        npc_catalog_path=args.npc_catalog,
        legacy_root=args.legacy,
        output=args.output,
    )


if __name__ == "__main__":
    main()
