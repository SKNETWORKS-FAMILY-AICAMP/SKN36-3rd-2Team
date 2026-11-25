"""Issue #165 - isolated staging vector ingestion."""

import argparse
import hashlib
import json
from pathlib import Path

from ollama import Client
from qdrant_client import QdrantClient

from crimescene.db.qdrant_collection import (
    ensure_qdrant_collection,
)
from crimescene.db.qdrant_sync import sync_qdrant_records
from crimescene.ingest.expanded_dataset import (
    COLLECTION,
    DRAFT_FLAG,
    load_verified_dataset,
)
from crimescene.ingest.ollama_embedder import OllamaEmbedder

LEGACY_COLLECTION = "case001_rag_v1"
REVISION1_COLLECTION = "case001_rag_1120_revision1"
REVISION2_COLLECTION = "case001_rag_1120_revision2"



def validate_revision2(root, docs, cards, policies):
    manifest = json.loads(
        (root / "manifest.json").read_text(
            encoding="utf-8-sig"
        )
    )

    revision = manifest.get("revision", {})

    if (
        revision.get("id") != "revision2"
        or revision.get("e26_section") != "A"
        or revision.get("review_status") != "PENDING"
        or manifest.get("runtime_enabled") is not False
        or manifest.get("status") != "STAGING_ONLY"
    ):
        raise PermissionError("Invalid revision2 manifest")

    e26_docs = [
        doc for doc in docs
        if "E26" in doc.source_evidence_ids
    ]

    if len(e26_docs) != 1:
        raise PermissionError("Expected exactly one E26 document")

    doc = e26_docs[0]
    policy = policies.get(doc.policy_id)

    required_flags = {
        DRAFT_FLAG,
        "ACT_AUDIT_LOG_ACCESS_VERIFIED",
    }

    actual_hash = hashlib.sha256(
        doc.body.encode("utf-8")
    ).hexdigest()

    if (
        doc.doc_id != "DOC-1120-E26-A"
        or doc.policy_id != "POL-1120-DOC-E26-A"
        or doc.case_id != "CASE-001"
        or doc.content_version != "case001_1120"
        or doc.source_evidence_ids != ["E26"]
        or doc.family != "evidence"
        or doc.access_scope != "collected_evidence"
        or doc.required_evidence != ["E20", "E26"]
        or set(doc.required_flags) != required_flags
        or doc.content_hash != actual_hash
        or revision.get("e26_content_sha256") != actual_hash
        or doc.search_text != (doc.title + chr(10) + doc.body)
    ):
        raise PermissionError("Unsafe E26-A document")

    if (
        policy is None
        or policy.required_evidence != ["E20", "E26"]
        or set(policy.required_flags) != required_flags
    ):
        raise PermissionError("Unsafe E26-A policy")

    if sum(
        item.policy_id == doc.policy_id for item in docs
    ) + sum(
        item.get("policy_id") == doc.policy_id for item in cards
    ) != 1:
        raise PermissionError("Shared E26-A policy")

    if any(
        "E30" in item.source_evidence_ids
        for item in docs
    ):
        raise PermissionError("Protected E30 document")

    if not all(
        DRAFT_FLAG in item.required_flags
        for item in policies.values()
    ):
        raise PermissionError("Missing staging denial flag")

    for card in cards:
        card_policy = policies[card["policy_id"]]

        if (
            "E26" in card_policy.required_evidence
            or any(
                value.endswith(":E26")
                for value in card_policy.required_presentations
            )
            or "E26" in json.dumps(card, ensure_ascii=False)
        ):
            raise PermissionError(
                f"Unreviewed E26 NPC card: {card['id']}"
            )

    print("REVISION2 SECURITY VALIDATION: PASS")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")

    parser.add_argument(
        "--collection",
        choices=[COLLECTION, REVISION2_COLLECTION],
        default=COLLECTION,
    )

    args = parser.parse_args()

    collection = args.collection

    records, docs, cards, policies = load_verified_dataset(
        args.root,
        expected_collection=collection,
    )

    if collection == REVISION2_COLLECTION:
        validate_revision2(
            args.root, docs, cards, policies
        )

    client = QdrantClient(
        url="http://127.0.0.1:6333",
        timeout=120,
    )

    embedder = OllamaEmbedder(
        model="bge-m3",
        client=Client(
            host="http://127.0.0.1:11434",
            timeout=120,
        ),
    )

    try:
        if not client.collection_exists(LEGACY_COLLECTION):
            raise ValueError("Legacy collection unavailable")

        legacy_before = client.count(
            collection_name=LEGACY_COLLECTION,
            exact=True,
        ).count

        protected_counts = {}

        if collection == REVISION2_COLLECTION:
            for name in (
                COLLECTION,
                REVISION1_COLLECTION,
            ):
                if not client.collection_exists(name):
                    raise ValueError(
                        f"Protected collection unavailable: {name}"
                    )

                protected_counts[name] = client.count(
                    collection_name=name,
                    exact=True,
                ).count

                print(
                    "PROTECTED BEFORE:",
                    name,
                    protected_counts[name],
                )

        print("LEGACY POINTS BEFORE:", legacy_before)
        print("STAGING COLLECTION:", collection)
        print("EXPECTED STAGING POINTS:", len(records))

        if not client.collection_exists(collection):
            if not args.apply:
                print("PLAN: CREATE STAGING COLLECTION")
                print("PLAN: ADD", len(records))
                print("DRY RUN ONLY")
                return

            ensure_qdrant_collection(
                client,
                collection_name=collection,
            )

        options = {
            "client": client,
            "embedder": embedder,
            "document_ids": {
                doc.doc_id for doc in docs
            },
            "npc_card_ids": {
                card["id"] for card in cards
            },
            "valid_policy_ids": set(policies),
            "collection_name": collection,
        }

        plan = sync_qdrant_records(
            records,
            dry_run=True,
            **options,
        )

        print("ADD:", len(plan.added))
        print("UPDATE:", len(plan.updated))
        print("UNCHANGED:", len(plan.unchanged))
        print("DELETE:", len(plan.deleted))

        if plan.deleted or plan.updated:
            raise ValueError("Unexpected staging changes")

        existing_count = client.count(
            collection_name=collection,
            exact=True,
        ).count

        if existing_count != len(plan.unchanged):
            raise ValueError("Unexpected existing points")

        if not args.apply:
            print("DRY RUN ONLY")
            return

        sync_qdrant_records(
            records,
            dry_run=False,
            allow_delete=False,
            **options,
        )

        final = sync_qdrant_records(
            records,
            dry_run=True,
            **options,
        )

        if final.total_changes:
            raise RuntimeError("Staging synchronization mismatch")

        staging_count = client.count(
            collection_name=collection,
            exact=True,
        ).count

        legacy_after = client.count(
            collection_name=LEGACY_COLLECTION,
            exact=True,
        ).count

        if staging_count != len(records):
            raise RuntimeError("Staging count mismatch")

        if legacy_after != legacy_before:
            raise RuntimeError("Legacy collection modified")

        for name, expected in protected_counts.items():
            actual = client.count(
                collection_name=name,
                exact=True,
            ).count

            if actual != expected:
                raise RuntimeError(
                    f"Protected collection modified: {name}"
                )

            print("PROTECTED AFTER:", name, actual)

        print("STAGING POINTS:", staging_count)
        print("LEGACY POINTS AFTER:", legacy_after)
        print("FINAL CHANGES:", final.total_changes)
        print("QDRANT STAGING INGEST COMPLETE")

    finally:
        client.close()


if __name__ == "__main__":
    main()
