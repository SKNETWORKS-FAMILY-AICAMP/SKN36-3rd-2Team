"""Release-bound RAG dataset selection."""

import hashlib
import json
from pathlib import Path

from crimescene.ingest.expanded_dataset import COLLECTION

REVISION1_COLLECTION = "case001_rag_1120_revision1"
REVISION2_COLLECTION = "case001_rag_1120_revision2"

E26_DOC_ID = "DOC-1120-E26-A"
E26_POLICY_ID = "POL-1120-DOC-E26-A"
E26_ACTION_FLAG = "ACT_AUDIT_LOG_ACCESS_VERIFIED"
DRAFT_FLAG = "INTERNAL_DRAFT_NOT_PUBLISHED"

REVISED_EVIDENCE = frozenset({"E03", "E06"})


def resolve_rag_binding(
    manifest: dict,
    dataset_root: Path,
) -> tuple[Path, str]:
    """Resolve an explicitly approved dataset and collection."""
    approved = manifest["approved_evidence"]
    binding = manifest.get("rag_binding")

    if "E26" in approved:
        if (
            manifest.get("approved_e26_sections") != ["A"]
            or not isinstance(binding, dict)
            or binding.get("dataset_revision") != "revision2"
        ):
            raise PermissionError(
                "E26-A requires explicit revision2 binding"
            )

    if binding is None:
        if REVISED_EVIDENCE.intersection(approved):
            raise PermissionError("Revised evidence requires RAG binding")

        return dataset_root, COLLECTION

    if not isinstance(binding, dict):
        raise TypeError("Invalid RAG binding")

    if set(binding) != {
        "dataset_revision",
        "collection",
        "manifest_sha256",
    }:
        raise ValueError("Invalid RAG binding fields")

    revisions = {
        "revision1": REVISION1_COLLECTION,
        "revision2": REVISION2_COLLECTION,
    }

    revision = binding["dataset_revision"]

    if (
        not isinstance(revision, str)
        or revision not in revisions
        or binding["collection"] != revisions[revision]
    ):
        raise PermissionError("Unapproved RAG revision")

    if revision == "revision2" and "E26" not in approved:
        raise PermissionError("Revision2 requires E26-A approval")

    selected_collection = revisions[revision]

    target = (
        dataset_root.parent
        / f"case001_1120_rag_{revision}"
    )
    manifest_path = target / "manifest.json"

    actual_hash = hashlib.sha256(
        manifest_path.read_bytes()
    ).hexdigest()

    if actual_hash != binding["manifest_sha256"]:
        raise ValueError("RAG manifest hash mismatch")

    dataset_manifest = json.loads(
        manifest_path.read_text(encoding="utf-8-sig")
    )

    if dataset_manifest["collection"] != selected_collection:
        raise ValueError("RAG collection mismatch")

    if revision == "revision2":
        metadata = dataset_manifest.get("revision", {})

        if (
            metadata.get("id") != "revision2"
            or metadata.get("e26_section") != "A"
            or dataset_manifest.get("status") != "STAGING_ONLY"
            or dataset_manifest.get("runtime_enabled") is not False
        ):
            raise PermissionError("Invalid revision2 dataset")

    return target, selected_collection

def validate_e26_rag_publication(
    manifest,
    documents,
    cards,
    policies,
):
    """Approve only the reviewed E26-A document and policy."""

    approved = manifest["approved_evidence"]

    documents = tuple(documents)
    cards = tuple(cards)

    e26_docs = [
        doc for doc in documents
        if "E26" in doc.source_evidence_ids
    ]

    if "E26" not in approved:
        if e26_docs:
            raise PermissionError("Unpublished E26 document")

        return

    binding = manifest.get("rag_binding")

    if (
        manifest.get("approved_e26_sections") != ["A"]
        or not isinstance(binding, dict)
        or binding.get("dataset_revision") != "revision2"
        or binding.get("collection") != REVISION2_COLLECTION
        or len(e26_docs) != 1
    ):
        raise PermissionError("Invalid E26 publication scope")

    doc = e26_docs[0]
    policy = policies.get(doc.policy_id)

    body_hash = hashlib.sha256(
        doc.body.encode("utf-8")
    ).hexdigest()

    approved_hash = approved["E26"].get(
        "section_a_content_sha256"
    )

    required_flags = {
        DRAFT_FLAG,
        E26_ACTION_FLAG,
    }

    if (
        doc.doc_id != E26_DOC_ID
        or doc.policy_id != E26_POLICY_ID
        or doc.case_id != "CASE-001"
        or doc.content_version != "case001_1120"
        or doc.state_version != "case001_1120"
        or doc.family != "evidence"
        or doc.access_scope != "collected_evidence"
        or doc.source_evidence_ids != ["E26"]
        or doc.required_evidence != ["E20", "E26"]
        or set(doc.required_flags) != required_flags
        or doc.required_presentations
        or doc.required_ending is not None
        or doc.protected_fact_ids
        or doc.content_hash != body_hash
        or approved_hash != body_hash
        or doc.search_text != (
            doc.title + chr(10) + doc.body
        )
    ):
        raise PermissionError("Unsafe E26-A publication")

    if (
        policy is None
        or policy.required_evidence != ["E20", "E26"]
        or set(policy.required_flags) != required_flags
        or policy.required_presentations
        or policy.required_topics
        or policy.required_disclosed_cards
        or policy.required_ending is not None
        or policy.required_character is not None
        or policy.required_npc_stage is not None
    ):
        raise PermissionError("Unsafe E26-A access policy")

    policy_users = sum(
        item.policy_id == doc.policy_id
        for item in documents
    ) + sum(
        card.get("policy_id") == doc.policy_id
        for card in cards
    )

    if policy_users != 1:
        raise PermissionError("Shared E26-A publication policy")

    for card in cards:
        card_policy = policies.get(card.get("policy_id"))

        if card_policy is None:
            raise PermissionError("Missing NPC policy")

        if (
            "E26" in card_policy.required_evidence
            or any(
                item.endswith(":E26")
                for item in card_policy.required_presentations
            )
            or "E26" in json.dumps(card, ensure_ascii=False)
        ):
            raise PermissionError("Unreviewed E26 NPC card")
